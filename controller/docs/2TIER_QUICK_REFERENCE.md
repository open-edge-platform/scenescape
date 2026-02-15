<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# 2-Tier Hybrid Search - Quick Reference

## For Developers

### Understanding the Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      sscape_object                              │
│  {                                                              │
│    "category": "person",    ← Generic (filtered)               │
│    "confidence": 0.95,      ← Generic (filtered)               │
│    "center_of_mass": {...}, ← Generic (filtered)               │
│    "age": "22",             ← Semantic (extracted) ✓           │
│    "gender": "Female",      ← Semantic (extracted) ✓           │
│    "person-attributes": "...", ← Semantic (extracted) ✓        │
│    "reid": [256-dim vector] ← Visual embedding (used in TIER 2)│
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│         uuid_manager._extractSemanticMetadata()                │
│  Returns: {"age": "22", "gender": "Female", ...}             │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│         uuid_manager.sendSimilarityQuery()                      │
│  Passes metadata constraints to database for filtering          │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│       vdms_adapter.findMatches(**constraints)         │
│                                                                │
│  TIER 1: Build constraints and filter at DB level            │
│  constraints = {                                              │
│    "type": ["==", "person"],    # Always included            │
│    "gender": ["==", "Female"],  # From metadata              │
│    "age": ["==", "22"]          # From metadata              │
│  }                                                             │
│                                                                │
│  TIER 2: Vector similarity on filtered candidates            │
│  "Compute L2 distance between query vector and                │
│   candidates that match TIER 1 constraints"                  │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Results                                      │
│  [                                                              │
│    {"uuid": "...", "rvid": "...", "_distance": 0.35},        │
│    {"uuid": "...", "rvid": "...", "_distance": 0.42},        │
│    ...                                                         │
│  ]                                                             │
└─────────────────────────────────────────────────────────────────┘
```

## Key Methods

### `uuid_manager._extractSemanticMetadata(sscape_object)`

**Purpose**: Automatically extract semantic attributes from detection object

**Input**: sscape_object with detection data
**Output**: Dictionary of semantic attributes

**Example**:

```python
metadata = uuid_manager._extractSemanticMetadata(sscape_object)
# If sscape_object has: {"age": "22", "gender": "Female", "confidence": 0.95}
# Returns: {"age": "22", "gender": "Female"}
#          (confidence excluded as generic property)
```

**What gets included**:

- ✅ Custom attributes: age, gender, color, make, model, person-attributes, etc.
- ✅ Any new field added to sscape_object by analytics pipeline
- ❌ Generic properties: category, confidence, center_of_mass, bounding_box_px
- ❌ System fields: rv_id, gid, uuid, reid
- ❌ Internal fields: anything starting with `_`

### `uuid_manager.sendSimilarityQuery(sscape_object)`

**Purpose**: Send 2-tier hybrid search query to database

**TIER 1**: Extract metadata → Build constraints → Filter at database
**TIER 2**: Compute L2 distance on filtered candidates

**Example**:

```python
# Object with metadata
sscape_object.age = "22"
sscape_object.gender = "Female"

# Internally:
# 1. Extracts: {"age": "22", "gender": "Female"}
# 2. Builds constraints: {"type": "person", "age": "22", "gender": "Female"}
# 3. Queries: "Find person where age=22 AND gender=Female, then compute L2"
scores = uuid_manager.sendSimilarityQuery(sscape_object)
```

### `vdms_adapter.findMatches(object_type, reid_vectors, **constraints)`

**Purpose**: Execute 2-tier query at database level

**TIER 1 Filtering**:

```python
constraints = {"age": "22", "gender": "Female"}
# Built in database query as:
query_constraints = {
  "type": ["==", object_type],
  "age": ["==", "22"],
  "gender": ["==", "Female"]
}
```

**TIER 2 Similarity**:

```python
# VDMS executes: Find entries matching constraints, compute L2 distance
# Returns: Top-k results sorted by distance
```

### `vdms_adapter.addEntry(uuid, rvid, object_type, reid_vectors, **metadata)`

**Purpose**: Store visual embedding + semantic metadata

**Storage**:

```python
# metadata passed as kwargs becomes properties
metadata = {"age": "22", "gender": "Female"}
vdms_adapter.addEntry(uuid, rvid, "person", reid_vectors, **metadata)

# Stored as:
properties = {
  "uuid": "...",
  "rvid": "...",
  "type": "person",
  "age": "22",        # From metadata
  "gender": "Female"  # From metadata
}
```

## Common Patterns

### Pattern 1: Query with All Available Metadata

```python
# All metadata from object automatically used for filtering
scores = uuid_manager.sendSimilarityQuery(sscape_object)
# If object has age, gender, color → All used in TIER 1 filtering
```

### Pattern 2: Query with Partial Metadata

```python
# Only specified constraints used for filtering
metadata = {"gender": "Female"}  # Only gender filtered
# Automatically called internally by sendSimilarityQuery()
```

### Pattern 3: Store Object with Metadata

```python
# When track ends, features stored with metadata
# Automatic via updateActiveDict() and _addNewFeaturesToDatabase()
# Metadata extracted once and stored persistently
```

### Pattern 4: Graceful Degradation

```python
# Query works even if some records lack metadata
# E.g., find Person where gender="Female"
# - Records with gender="Female" → Included
# - Records without gender field → Excluded by constraint
# - Mixed old/new records coexist
```

## Backward Compatibility

### Before Implementation

```python
# Single-tier: Only visual embedding used
scores = self.reid_database.findMatches(object_type, reid_vectors)
```

### After Implementation (Fully Compatible)

```python
# Still works! Metadata constraints optional
scores = self.reid_database.findMatches(object_type, reid_vectors)
# Same as: findMatches(object_type, reid_vectors, **{})
# Empty constraints → No TIER 1 filtering → Same results
```

## Testing Checklist

- [ ] `_extractSemanticMetadata()` correctly identifies semantic vs generic
- [ ] TIER 1 filtering works with single constraint
- [ ] TIER 1 filtering works with multiple constraints
- [ ] TIER 2 similarity computed on filtered candidates only
- [ ] Query works with NO constraints (backward compat)
- [ ] Query works with PARTIAL constraints
- [ ] Old records (no metadata) still queryable
- [ ] Mixed old/new records coexist in database
- [ ] Metadata stored with embeddings correctly
- [ ] Retrieved results include all properties

## Future Phases

### Phase 2: Confidence & Versioning

```python
metadata = {
  "confidence_scores": {"color": 0.95, "age": 0.88},  # Dict serialized as JSON
  "versioning": {"model": "v2.1", "timestamp": "..."}
}
vdms_adapter.addEntry(uuid, rvid, type, reid_vectors, **metadata)

# Query with parsed metadata:
scores = json.loads(result['confidence_scores'])
if scores['color'] > 0.9:  # Application-level filtering
  return result
```

### Phase 3: Spatio-Temporal

```python
metadata = {
  "position": {"x": 123.45, "y": 456.78, "z": 10.5},  # Stored as JSON
  "timestamp": "2026-02-06T11:37:26.093Z"
}
# TIER 1: Filter by timestamp range (application-level)
# TIER 2: Spatial consistency check via distance calculation
```

## References

- Full Implementation: controller/docs/2TIER_HYBRID_SEARCH_IMPLEMENTATION.md
- Architecture Decision: docs/adr/0010-reid-metadata-storage-architecture.md
- Modified Files:
  - controller/src/controller/reid.py
  - controller/src/controller/vdms_adapter.py
  - controller/src/controller/uuid_manager.py
