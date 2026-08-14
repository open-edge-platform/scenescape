<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# 2-Tier Hybrid Search Implementation

## Overview

This document describes the implementation of 2-tier hybrid search for Re-ID (Re-Identification) in the Scene Controller, as specified in [ADR-0010](https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0010-reid-metadata-storage-architecture.md).

**Architecture**: TIER 1 (metadata filtering) + TIER 2 (vector similarity)

```text
ReID Query Flow (VDMS or Qdrant):

  sscape_object with semantic metadata (age, gender, color, etc.)
    ↓
  Extract semantic attributes via _extractSemanticMetadata()
    ↓
  sendSimilarityQuery() calls findMatches() with constraints
    ↓
  TIER 1: Backend applies metadata constraints (exact-match filtering)
    "Find entries where type='Person' AND gender='Female' AND age='22'"
    ↓
  TIER 2: Backend performs vector similarity on filtered candidates
    "Compute configured similarity metric value between query vector and filtered candidates"
    ↓
  Return top-k matches with metadata
```

## Key Concepts

### Similarity Metric and Score Semantics

The Re-ID metric is configured through `reid-config.json` (`similarity_metric`) and defaults to `COSINE`.

When `similarity_metric` is `COSINE`, Re-ID embedding vectors are normalized to unit length before they are:

- stored in the ReID vector database
- used as query vectors for similarity search

For `COSINE`, Scenescape uses an inner-product path with normalized vectors (VDMS `IP`; Qdrant DOT), so similarity scores are expected to stay in the range `[-1, 1]`.

- `1.0`: identical direction (most similar)
- `0.0`: orthogonal embeddings
- `-1.0`: opposite direction

The controller validates returned similarity scores for the normalized-cosine path (`COSINE` mapped to backend IP/DOT) and discards out-of-range values. For non-cosine distance metrics (for example `L2`), vectors are not force-normalized and this `[-1, 1]` check is not applied.

### Limitations

- Extended ReID is not compatible with the `--pose-adjustment` controller flag. When pose-based bounding box adjustment is enabled, Extended ReID must be disabled.
- Cameras using pose estimation pipelines with `gvainference` + `gvatrack` (e.g. `mars-small128` + `yolo11n-pose` for deep-sort tracking) cannot use `reidPolicy` as their metadata generation policy. These cameras must use `detectionPolicy`.

### Confidence-Based Constraint Filtering (AND-Only)

The 2-tier implementation uses metadata confidence scores to determine which constraints are applied in TIER 1 filtering. **Only high-confidence (≥ 0.8) constraints are used for strict AND filtering**. Low-confidence constraints are skipped in TIER 1, allowing TIER 2 vector similarity to handle flexible matching:

```text
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

```text
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

Shared `REID_*` settings configure any vector backend. Only `REID_DATABASE` selects which adapter runs. Hostname, port, TLS, and certificate paths are backend-agnostic (`reid.scenescape.intel.com:55555`, TLS on, `scenescape-reid*` / CA paths).

| Variable                                                | Purpose                              | Default                                                             |
| ------------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------- |
| `REID_DATABASE`                                         | Backend (`VDMS` or `QDRANT`)         | `VDMS`                                                              |
| `REID_HOSTNAME`                                         | Database host                        | `reid.scenescape.intel.com`                                         |
| `REID_PORT`                                             | Database port (1–65535)              | `55555`                                                             |
| `REID_USE_TLS`                                          | TLS on/off (`true`/`false`)          | `true`                                                              |
| `REID_API_KEY`                                          | Optional API key                     | unset                                                               |
| `REID_CONFIDENCE_THRESHOLD`                             | TIER 1 metadata confidence threshold | `0.8`                                                               |
| `REID_CA_CERT` / `REID_CLIENT_CERT` / `REID_CLIENT_KEY` | TLS / mTLS paths                     | `scenescape-ca.pem` / `scenescape-reid.crt` / `scenescape-reid.key` |

- Values ≥ `REID_CONFIDENCE_THRESHOLD`: Included in AND constraints (strict metadata filtering)
- Values < threshold: Ignored (rely on TIER 2 vector similarity for flexible matching)
- Valid range: 0.0 to 1.0
- To select a backend in a deployment, see [Selecting the ReID Vector Database Backend](../../other-topics/how-to-enable-reidentification.md#selecting-the-reid-vector-database-backend)

Backend-prefixed names such as `VDMS_HOSTNAME` or `QDRANT_PORT` are no longer read. Set the `REID_*` equivalent instead.

These values are validated when the controller starts. A port outside 1–65535, a threshold outside 0.0–1.0, or a boolean the parser does not recognize (anything other than `1`/`true`/`yes`/`on` or `0`/`false`/`no`/`off`, case-insensitive) aborts startup with a message naming the variable and its value. Nothing silently falls back to a default — in particular, a misspelled `REID_USE_TLS` will not quietly drop the connection to plaintext. Blank values are treated as unset.

## Configuring Confidence Threshold

The confidence threshold determines which metadata constraints are applied in TIER 1 filtering. Only constraints meeting or exceeding the threshold are used. Constraints below the threshold are skipped, allowing vector similarity in TIER 2 to handle the matching:

```bash
# In the controller service environment in docker-compose.yml or .env file
REID_CONFIDENCE_THRESHOLD=0.85

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
  "similarity_metric": "COSINE",
  "stale_feature_timeout_secs": 5.0,
  "stale_feature_check_interval_secs": 1.0,
  "feature_accumulation_threshold": 12,
  "minimum_bbox_area": 5000,
  "feature_slice_size": 10,
  "similarity_threshold": 0.5
}
```

### Configuration Parameters

| Parameter                           | Type   | Default                                                | Description                                                                                                                                                                                                      |
| ----------------------------------- | ------ | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `similarity_metric`                 | string | `COSINE`                                               | Similarity metric for ReID matching. `COSINE` is the default and uses normalized vectors with an inner-product backend path (higher-is-better). `L2` provides distance-style matching (lower-is-better).         |
| `stale_feature_timeout_secs`        | float  | 5.0                                                    | How long (seconds) to accumulate features in memory before flushing to the ReID database. Features older than this threshold are persisted for long-term storage.                                                |
| `stale_feature_check_interval_secs` | float  | 1.0                                                    | How frequently (seconds) the background timer checks for stale features and flushes them to the ReID database. More frequent checks ensure timely database updates.                                              |
| `feature_accumulation_threshold`    | int    | 12                                                     | Minimum number of quality features required before initiating a similarity query against the database. More features = higher statistical confidence in matching.                                                |
| `minimum_bbox_area`                 | int    | 5000                                                   | Minimum pixel-space bounding-box area a detection must have for its ReID embedding to be used. Applied by the scene that owns the camera, since it is the only scope that has the source crop to measure.        |
| `feature_slice_size`                | int    | 10                                                     | When persisting features to the ReID database, sample every Nth feature vector from the accumulated set to reduce database bloat. Example: slice_size=10 stores every 10th vector.                               |
| `similarity_threshold`              | float  | metric-dependent (`40.0` for `L2`, `0.5` for `COSINE`) | Match acceptance threshold interpreted using the configured metric semantics: for `COSINE`, candidates **above** the threshold match; for `L2`-style distance metrics, candidates **below** the threshold match. |

**Similarity range note**: For `COSINE` (normalized vectors with backend IP/DOT), scores are validated against `[-1, 1]` because embeddings are normalized before storage and query. This range check is metric-specific and is not applied to non-cosine distance metrics.

> **Migration note:** Existing ReID schemas or collections created with `L2`
> are not compatible with the new `COSINE` default. Recreate the backend data
> store before starting the controller, or explicitly keep
> `"similarity_metric": "L2"` with an L2 threshold.

### Embeddings in a Scene Hierarchy

Independent scenes that are **not** linked as parent/child may **share** one
ReID database or use **separate** instances.

Scenes in a [hierarchy](../../how-to-guides/build-a-scene/configure-hierarchy-of-scenes.md)
must not use **split** ReID databases across children (or child vs parent) when
the parent should unify people. Supported layouts include shared ReID on parent
and children, **parent-only ReID** with children forwarding embeddings (parent
enrolls on query-no-match), or no ReID. See
[ReID across controllers](../../how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md#reid-across-controllers-what-is-supported).
With **local** children, one controller owns ReID for the whole hierarchy.
Each embedding still has to be attributable to exactly one enrollment:

- **Quality is judged once, where the pixels are.** A scene applies `minimum_bbox_area` to
  detections from its own cameras. Objects forwarded from a child arrive in world coordinates
  with no pixel bounding box, so there is nothing left to measure at the parent.
- **Forwarded embeddings state their origin.** When a child publishes to its parent, an embedding
  that passed the gate travels with the id of the originating scene and camera and a
  `quality_vetted` flag. Embeddings that failed the gate, or that no scope can vouch for, are not
  forwarded at all.
- **Query first, then write under one UUID.** A detection from a camera on this
  controller may be enrolled when the bbox passes `minimum_bbox_area`. A parent
  with `Retrack` enabled may **query** with forwarded embeddings that carry
  vetted provenance. On no-match it may sole-enroll those features when the
  child did **not** claim write authority (parent-only ReID / passthrough). On
  match it rematches and may **enhance** that UUID's embedding cluster with
  further forwarded vectors unless upstream stamped `will_enroll` / `enrolled`.
  Exact duplicate vectors are not stored again. Parent-owned cameras still
  enroll on the parent as usual.
- **Write authority on hierarchy output.** A ReID-enabled publisher withholds
  **local** hierarchy reid until the vector schema is ready **and** at least one
  database write has succeeded, then stamps `will_enroll` (and `enrolled` once
  the track owns a write). If database writes later fail, publish drops to
  passthrough and local enrollment stops so a parent can sole-enroll without
  racing the child. Children without ReID write intent never set those flags.
  See
  [write authority](../../how-to-guides/build-a-scene/deploy-multi-controller-on-one-host.md#write-authority-on-the-hierarchy-wire-will_enroll--enrolled).
- **Live-gid collision limits concurrent Rematch.** A parent will not assign the same database
  UUID to two concurrent live tracks. Cross-child identity continuity via ReID is therefore
  verified for **sequential** rematch today; concurrent two-child merge via ReID alone is a
  [product follow-up](../../../adr/0015-hierarchy-reid-provenance.md#how-should-two-live-parent-tracks-share-one-reid-database-identity).
- **Provenance is not accepted from detectors.** Origin claims arriving on a camera topic are
  discarded, so a detector cannot bypass the bounding-box quality gate.

### Embedding Dimension Inference

The controller automatically infers the ReID embedding dimension from the first vector it receives at runtime:

- **Runtime inference only**: On the first decoded embedding the controller reads the vector length from the payload, creates the backend schema/collection with that dimension, and locks that dimension for the process lifetime. All subsequent embeddings are validated against that inferred length; mismatches are discarded with a warning.
- **Switching ReID models**: Because the dimension is locked after the first embedding, switching to a model with a different output length requires restarting the controller. The backend schema/collection must also be recreated if the stored dimension differs (in-place schema migration is not supported).
- **Base64 compatibility**: The controller decodes base64 embeddings using the payload byte length by default. Producers can also include an optional `embedding_dimensions` field alongside `embedding_vector`; if provided, it must match the packed float count.

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

- `similarity_metric`, `stale_feature_timeout_secs`, `stale_feature_check_interval_secs`, `feature_accumulation_threshold`, `minimum_bbox_area`, `feature_slice_size`, and `similarity_threshold` are fully implemented
- ReID embedding dimensions are inferred at runtime from the first received embedding; there is no configuration override for dimension.
- All semantic metadata attributes are currently used for TIER 1 filtering. Selective metadata filtering is planned for Phase 2.

### Tuning Recommendations

**For Higher Recall (more matches found)**:

- Decrease `stale_feature_timeout_secs`: 3.0 (flush features sooner, capture recent appearances)
- Decrease `stale_feature_check_interval_secs`: 0.5 (check for stale features more frequently)
- Decrease `feature_accumulation_threshold`: 8 (query sooner with fewer features)
- `similarity_threshold` — direction depends on the configured metric:
  - **`COSINE` (default)**: _Decrease_ the threshold (e.g., 0.2) to accept candidates with lower cosine similarity → more matches
  - **`L2`**: _Increase_ the threshold (e.g., 50.0) to accept candidates further away → more matches
- Increase `feature_slice_size`: 20 (store more diverse samples)

**For Higher Precision (only confident matches)**:

- Increase `stale_feature_timeout_secs`: 8.0 (accumulate more features before persisting)
- Increase `stale_feature_check_interval_secs`: 2.0 (check less frequently, reduce overhead)
- Increase `feature_accumulation_threshold`: 16 (require more samples for statistical confidence)
- `similarity_threshold` — direction depends on the configured metric:
  - **`COSINE` (default)**: _Increase_ the threshold (e.g., 0.8) to accept only high-cosine-similarity candidates → fewer, more confident matches
  - **`L2`**: _Decrease_ the threshold (e.g., 20.0) so only close-distance candidates match → fewer, more confident matches
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

- [How to enable re-identification](../../other-topics/how-to-enable-reidentification.md) (including VDMS ↔ Qdrant switch)
- [VDMS Documentation](https://github.com/IntelLabs/vdms)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
