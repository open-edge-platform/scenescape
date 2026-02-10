<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# 2-Tier Hybrid Search Implementation

## Overview

This document describes the implementation of 2-tier hybrid search for Re-ID (Re-Identification) in the Scene Controller, as specified in ADR-0010.

**Architecture**: TIER 1 (metadata filtering) + TIER 2 (vector similarity)

```
VDMS Query Flow:

  sscape_object with semantic metadata (age, gender, color, etc.)
    ↓
  Extract semantic attributes via _extractSemanticMetadata()
    ↓
  sendSimilarityQuery() calls findMatches() with constraints
    ↓
  TIER 1: VDMS applies metadata constraints (exact-match filtering)
    "Find entries where type='Person' AND gender='Female' AND age='22'"
    ↓
  TIER 2: VDMS performs vector similarity on filtered candidates
    "Compute L2 distance between query vector and filtered candidates"
    ↓
  Return top-k matches with metadata
```

## Implementation Details

### 1. Metadata Extraction (`uuid_manager._extractSemanticMetadata()`)

Automatically extracts semantic attributes from sscape_object by filtering out generic properties.

**Generic properties excluded**:

- `category`, `confidence`, `center_of_mass`, `bounding_box_px` (object properties)
- `rv_id`, `gid`, `uuid`, `reidVector` (system fields)
- `reid` (the visual embedding itself)
- Any field starting with `_` (internal fields)

**Semantic attributes included** (automatically passed through):

- `age`, `gender`, `person-attributes` (for Person objects)
- `color`, `make`, `model`, `license_plate` (for Vehicle objects)
- Any future attributes added by the analytics pipeline

**Example**:

```python
sscape_object = {
  "category": "person",          # Excluded (generic)
  "confidence": 0.95,            # Excluded (generic)
  "center_of_mass": {...},       # Excluded (generic)
  "age": "22",                   # Included (semantic)
  "gender": "Female",            # Included (semantic)
  "person-attributes": "..."     # Included (semantic)
  "reid": [256-dim vector]       # Excluded (visual embedding)
}

# _extractSemanticMetadata() returns:
{
  "age": "22",
  "gender": "Female",
  "person-attributes": "..."
}
```

### 2. TIER 1: Metadata Filtering

In `sendSimilarityQuery()`, metadata constraints are passed to `findMatches()`:

```python
# Extract metadata from sscape_object
metadata_constraints = self._extractSemanticMetadata(sscape_object)

# Pass to database with query
scores = self.reid_database.findMatches(
  sscape_object.category,
  reid_vectors,
  **metadata_constraints  # TIER 1: Constraints for metadata filtering
)
```

In `vdms_adapter.findMatches()`, constraints are converted to VDMS query format:

```python
# Build dynamic constraints (TIER 1)
query_constraints = {
  "type": ["==", "Person"],        # Always filter by object type
  "gender": ["==", "Female"],      # Additional metadata constraints
  "age": ["==", "22"]
}

# Send to VDMS - filters happen at database level before vector search
find_query = {
  "FindDescriptor": {
    "set": "reid_vector",
    "constraints": query_constraints,  # TIER 1: Database-level filtering
    "k_neighbors": 5
  }
}
```

**Benefits of TIER 1**:

- ✅ Database-level filtering (reduces candidates before vector search)
- ✅ <1ms filtering overhead
- ✅ Eliminates obviously non-matching candidates
- ✅ Reduces TIER 2 computation cost

### 3. TIER 2: Vector Similarity

After TIER 1 filtering, VDMS performs vector similarity on the filtered candidates:

```python
# TIER 2: Vector similarity search on filtered candidates
# VDMS internally:
# 1. Apply constraints from TIER 1
# 2. Compute L2 distance between query vector and filtered candidates
# 3. Return top-k results sorted by distance
```

### 4. Storage with Metadata

When storing features in the database (`updateActiveDict()` and `_addNewFeaturesToDatabase()`):

```python
# Store features with semantic metadata
self.features_for_database[sscape_object.rv_id] = {
  'gid': database_id,
  'category': sscape_object.category,
  'reid_vectors': self.quality_features[sscape_object.rv_id],
  'metadata': self._extractSemanticMetadata(sscape_object)  # Metadata for storage
}

# When track ends, addEntry is called with metadata
self.reid_database.addEntry(
  uuid, rvid, object_type, reid_vectors,
  **metadata  # Stored as schema-less properties in VDMS
)
```

In `vdms_adapter.addEntry()`, metadata is stored as properties:

```python
# Store metadata as schema-less properties
for key, value in metadata.items():
  if isinstance(value, dict):
    properties[key] = json.dumps(value)  # Serialize dicts as JSON
  else:
    properties[key] = str(value)

# All stored together
query = {
  "AddDescriptor": {
    "set": "reid_vector",
    "properties": {
      "uuid": "...",
      "rvid": "...",
      "type": "Person",
      "age": "22",              # Metadata property
      "gender": "Female",       # Metadata property
      "person-attributes": "..." # Metadata property
    }
  }
}
```

## Backward Compatibility

- ✅ Objects without metadata continue to work (missing fields handled gracefully)
- ✅ Old records (without metadata) can coexist with new records (with metadata)
- ✅ No database migration needed when new metadata fields added
- ✅ Queries with partial constraints work (omitted fields skip that filtering)

**Example**: Query for Person objects without specifying age/gender:

```python
# Works even if some records have age/gender and others don't
metadata_constraints = {"gender": "Female"}
scores = self.reid_database.findMatches(
  "Person", reid_vectors,
  **metadata_constraints  # Only filters by gender, ignores age
)
```

## Phase Evolution

### Phase 1 (Current): Initial Semantic Metadata

- Person: age, gender, person-attributes
- Vehicle: color, make, model
- Automatic extraction via \_extractSemanticMetadata()
- 2-tier queries with metadata filtering

### Phase 2: Confidence Scores & Versioning

- Store confidence dicts: `{"color": 0.95, "make": 0.88}`
- Add versioning metadata: `{"model_version": "v2.1", "timestamp": "..."}`
- Application-level filtering on complex data types

### Phase 3: Spatio-Temporal Tracking

- Add position/orientation: `{"x": 123.45, "y": 456.78, "orientation": 45.0}`
- Add timestamp: `{"timestamp": "2026-02-06T11:37:26.093Z"}`
- Spatial radius queries via application-level post-processing

## Configuration

No configuration changes needed. Metadata extraction is automatic based on sscape_object structure.

**Environment variables** (existing):

- `VDMS_HOSTNAME`: VDMS server hostname (default: `vdms.scenescape.intel.com`)
- `REID_DATABASE`: Vector database backend (default: `VDMS`)

## Testing

Tests should verify:

1. ✅ Metadata extraction correctly identifies semantic vs generic properties
2. ✅ TIER 1 filtering works (constraints properly applied)
3. ✅ TIER 2 similarity works on filtered candidates
4. ✅ Backward compatibility (queries work with/without metadata)
5. ✅ Schema flexibility (new metadata fields accepted without code changes)
6. ✅ Storage and retrieval of metadata with reid vectors

## References

- ADR-0010: Re-ID Metadata Storage Architecture
- Scene Controller Agents.md: Architecture overview
- VDMS Documentation: https://github.com/IntelLabs/vdms
