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

## Key Concepts

### Confidence-Based Constraint Routing

The 2-tier implementation uses metadata confidence scores to intelligently route constraints as AND or OR:

```
High Confidence (≥ 0.8)        Low Confidence (< 0.8)
        ↓                                ↓
    AND Constraint              OR Constraint
        ↓                                ↓
   age = 22                    clothing = blue
   AND gender = Female         OR color = red
        ↓                                ↓
   Strict: All must match      Flexible: At least one
```

**Why AND for high confidence (≥ 0.8)?**

- Age + gender from same model (age-gender-recognition-retail-0013) typically both ~0.85-0.95 confidence
- Combining multiple high-confidence attributes = very reliable (significantly fewer false positives)
- Query: "Find Person where age=22 AND gender=Female" is specific and highly accurate
- Reduces false matches by requiring ALL high-confidence attributes to align

**Why OR for low confidence (< 0.8)?**

- Low-confidence attributes alone risk missing actual matches
- Offering alternatives with OR increases recall at acceptable cost
- Query: "Find Person where clothing=blue OR color=red" casts wider net
- Balances precision loss with gains in recall

**Mixed Confidence Example**:

```
Query: Person with age=25 (conf 0.92) AND gender=Male (conf 0.90)
                  OR eyewear=glasses (conf 0.55)

Logic: "Find strong age-gender matches, OR any Male wearing glasses"
       (If age/gender match is unavailable, relax to eyewear match)
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
- `VDMS_CONFIDENCE_THRESHOLD`: Confidence threshold for AND/OR constraint routing (default: `0.8`)
  - Values ≥ threshold: AND constraints (strict matching, all must match)
  - Values < threshold: OR constraints (flexible matching, at least one must match)
  - Valid range: 0.0 to 1.0
  - Example: Set to `0.7` for more flexible matching, `0.9` for stricter matching

### Configuring Confidence Threshold

The confidence threshold determines how metadata constraints are applied in TIER 1 filtering. Confidence threshold can be configured using:

```bash
# In the controller service environment in docker-compose.yml or .env file
VDMS_CONFIDENCE_THRESHOLD=0.85

# Launch controller with custom threshold
docker compose up -d
```

**Example Threshold Selection Guide**:

- `0.7`: More matches, higher recall (recommended for exploratory queries)
- `0.8`: **Default balanced approach** (recommended for most use cases)
- `0.9`: Fewer but highly accurate matches (recommended when precision is critical)

## Testing

Tests should verify:

1. ✅ Metadata extraction correctly identifies semantic vs generic properties
2. ✅ TIER 1 filtering works (constraints properly applied)
3. ✅ TIER 2 similarity works on filtered candidates
4. ✅ Backward compatibility (queries work with/without metadata)
5. ✅ Schema flexibility (new metadata fields accepted without code changes)
6. ✅ Storage and retrieval of metadata with reid vectors

## References

- ADR-0010: Re-ID Metadata Storage Architecture (https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0010-reid-metadata-storage-architecture.md)
- VDMS Documentation: https://github.com/IntelLabs/vdms

```

```
