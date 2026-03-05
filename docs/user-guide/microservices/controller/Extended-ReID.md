<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# 2-Tier Hybrid Search Implementation

## Overview

This document describes the implementation of 2-tier hybrid search for Re-ID (Re-Identification) in the Scene Controller, as specified in [ADR-0010](../../../adr/0010-reid-metadata-storage-architecture.md).

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

## Key Concepts

### Confidence-Based Constraint Filtering (AND-Only)

The 2-tier implementation uses metadata confidence scores to determine which constraints are applied in TIER 1 filtering. **Only high-confidence (≥ 0.8) constraints are used for strict AND filtering**. Low-confidence constraints are skipped in TIER 1, allowing TIER 2 vector similarity to handle flexible matching:

```
High Confidence (≥ 0.8)        Low Confidence (< 0.8)
        ↓                                ↓
    AND Constraint          IGNORED (rely on TIER 2)
        ↓                                ↓
   age = 22                       Skip
   AND gender = Female            ↓
        ↓                    Vector similarity
   TIER 1: Strict            finds matches
   metadata filter           based on embeddings
```

**Why AND for high confidence only (≥ 0.8)?**

- Age + gender from same model (age-gender-recognition-retail-0013) typically both ~0.85-0.95 confidence
- Combining multiple high-confidence attributes = very reliable (significantly fewer false positives)
- Query: "Find Person where age=22 AND gender=Female" is specific and highly accurate
- Reduces false matches by requiring ALL high-confidence attributes to align

**Why ignore low confidence (< 0.8)?**

- VDMS limitations: OR constraints across multiple properties are not well-supported
- Simplified design: Skip low-confidence filtering in TIER 1 entirely
- TIER 2 vector similarity provides flexible matching instead
- Query: "Find similar Persons" via vector embedding (ignores low-confidence metadata)
- Better approach: Rely on embedding distance rather than unreliable metadata

**Example**:

```
Query: Person with age=25 (conf 0.92), gender=Male (conf 0.90), eyewear=glasses (conf 0.55)

TIER 1 Filtering: age=25 AND gender=Male (high confidence applied)
                  eyewear=glasses IGNORED (low confidence - below 0.8 threshold)

TIER 2 Matching: Vector similarity finds closest matches among TIER 1 filtered candidates
                 The embedding distance handles eyewear and other low-confidence attributes

Result: "Find strong age-gender matches, refined by vector similarity"
```

## Backward Compatibility

- ✅ Objects without metadata continue to work (missing fields handled gracefully)
- ✅ Old records (without metadata) can coexist with new records (with metadata)
- ✅ No database migration needed when new metadata fields added
- ✅ Queries with partial constraints work (omitted fields skip that filtering)

## Phase Evolution

### Phase 1 (Current): Initial Semantic Metadata

- Person: age, gender, person-attributes
- Vehicle: color, make, model
- Automatic extraction via \_extractSemanticMetadata()
- 2-tier queries with metadata filtering

### Phase 2: Confidence Scores & Versioning

- Store confidence dicts: `{"color": 0.95, "make": 0.88}`
- Add model name and versioning metadata: `{"model_name": "age_gender", "model_version": "v2.1", "timestamp": "..."}`
- Application-level filtering on complex data types

### Phase 3: Spatio-Temporal Tracking

- Add position/orientation: `{"x": 123.45, "y": 456.78, "orientation": 45.0}`
- Add timestamp: `{"timestamp": "2026-02-06T11:37:26.093Z"}`
- Spatial radius queries via application-level post-processing

**Environment variables**:

- `VDMS_HOSTNAME`: VDMS server hostname (default: `vdms.scenescape.intel.com`)
- `REID_DATABASE`: Vector database backend (default: `VDMS`)
- `VDMS_CONFIDENCE_THRESHOLD`: Minimum confidence for applying constraints in TIER 1 (default: `0.8`)
  - Values ≥ threshold: Included in AND constraints (strict metadata filtering)
  - Values < threshold: Ignored (rely on TIER 2 vector similarity for flexible matching)
  - Valid range: 0.0 to 1.0
  - Example: Set to `0.7` to include more metadata filters, `0.9` for stricter filtering

## Configuring Confidence Threshold

The confidence threshold determines which metadata constraints are applied in TIER 1 filtering. Only constraints meeting or exceeding the threshold are used. Constraints below the threshold are skipped, allowing vector similarity in TIER 2 to handle the matching:

```bash
# In the controller service environment in docker-compose.yml or .env file
VDMS_CONFIDENCE_THRESHOLD=0.85

# Launch controller with custom threshold
docker compose up -d
```

**Example Threshold Selection Guide**:

- `0.7`: More metadata constraints applied, higher specificity in TIER 1 (may miss matches due to strict filtering)
- `0.8`: **Default balanced approach** (recommended for most use cases)
- `0.9`: Only highest-confidence metadata filters applied, rely more on TIER 2 vector similarity (highest recall)

## REID Configuration File

The Scene Controller now supports a dedicated `reid-config.json` configuration file for managing Re-ID specific settings. This file provides separation of concerns between tracker configuration (motion models, timing parameters) and Re-ID behavior (feature accumulation, database flushing, similarity thresholds).

### Configuration File Location

Place `reid-config.json` in the controller config directory:

```
controller/config/reid-config.json
```

### Sample Configuration

```json
{
  "stale_feature_timeout_secs": 5.0,
  "stale_feature_check_interval_secs": 1.0,
  "feature_accumulation_threshold": 12,
  "feature_slice_size": 10,
  "similarity_threshold": 60
}
```

### Configuration Parameters

| Parameter                           | Type  | Default | Description                                                                                                                                                           |
| ----------------------------------- | ----- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `stale_feature_timeout_secs`        | float | 5.0     | How long (seconds) to accumulate features in memory before flushing to VDMS. Features older than this threshold are persisted to the database for long-term storage.  |
| `stale_feature_check_interval_secs` | float | 1.0     | How frequently (seconds) the background timer checks for stale features and flushes them to VDMS. More frequent checks ensure timely database updates.                |
| `feature_accumulation_threshold`    | int   | 12      | Minimum number of quality features required before initiating a similarity query against the database. More features = higher statistical confidence in matching.     |
| `feature_slice_size`                | int   | 10      | When persisting features to VDMS, sample every Nth feature vector from the accumulated set to reduce database bloat. Example: slice_size=10 stores every 10th vector. |
| `similarity_threshold`              | int   | 60      | Minimum similarity score (0-100) for a match to be considered valid. Higher values = stricter matching.                                                               |

### Using the Configuration File

Pass the reid-config file path to the Scene Controller:

```bash
python scene_controller.py \
  --tracker_config_file controller/config/tracker_config.json \
  --reid_config_file controller/config/reid-config.json \
  --broker mqtt.example.com \
  --resturl http://rest.example.com
```

**Current Implementation Note**:

- `stale_feature_timeout_secs`, `stale_feature_check_interval_secs`, `feature_accumulation_threshold`, `feature_slice_size`, and `similarity_threshold` are fully implemented
- All semantic metadata attributes are currently used for TIER 1 filtering. Selective metadata filtering is planned for Phase 2.

### Tuning Recommendations

**For Higher Recall (more matches found)**:

- Decrease `stale_feature_timeout_secs`: 3.0 (flush features sooner, capture recent appearances)
- Decrease `stale_feature_check_interval_secs`: 0.5 (check for stale features more frequently)
- Decrease `feature_accumulation_threshold`: 8 (query sooner with fewer features)
- Decrease `similarity_threshold`: 50 (accept less-perfect matches)
- Increase `feature_slice_size`: 20 (store more diverse samples)

**For Higher Precision (only confident matches)**:

- Increase `stale_feature_timeout_secs`: 8.0 (accumulate more features before persisting)
- Increase `stale_feature_check_interval_secs`: 2.0 (check less frequently, reduce overhead)
- Increase `feature_accumulation_threshold`: 16 (require more samples for statistical confidence)
- Increase `similarity_threshold`: 75 (stricter matching)
- Decrease `feature_slice_size`: 5 (store every 5th feature for better coverage)

### Future Extensibility

The `reid-config.json` design is extensible for future REID enhancements:

- **Phase 2**: Confidence score thresholds per attribute type
- **Phase 3**: Model-specific configuration (reid model name, version)
- **Phase 4**: Spatio-temporal constraints (spatial radius, time window)
- **Phase 5**: Custom feature aggregation strategies

## Testing

Tests should verify:

1. ✅ Metadata extraction correctly identifies semantic vs generic properties
2. ✅ TIER 1 filtering works (constraints properly applied)
3. ✅ TIER 2 similarity works on filtered candidates
4. ✅ Backward compatibility (queries work with/without metadata)
5. ✅ Schema flexibility (new metadata fields accepted without code changes)
6. ✅ Storage and retrieval of metadata with reid vectors
7. ✅ Stale feature flushing respects configured timeout
8. ✅ Configuration file loading and parameter application

## References

- [VDMS Documentation](https://github.com/IntelLabs/vdms)
