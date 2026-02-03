# ADR 10: Extended Reidentification Architecture Using Embedding Vectors and Metadata Attributes

- **Author(s)**: Sarat Poluri, Claude Haiku 4.5
- **Date**: 2025-01-29
- **Status**: `Proposed`

## Context

SceneScape's Re-ID system currently stores only 256-dimensional float32 vectors in VDMS for object embeddings. However, real-world tracking scenarios require associating rich metadata with these embeddings:

- **Vehicle Re-ID**: color, make, model, license plate, body type
- **Person Re-ID**: clothing color, gender, age, height estimate, badge ID
- **Tracking Context**: detection timestamp, camera source
- **Model Metadata**: model version, model name

Additionally, during the lifetime of a system the inference pipeline can continue to evolve and include different metadata and embeddings.

Challenges with current approach:

1. **No metadata filtering**: Cannot constrain vector searches by object attributes before similarity search
2. **Performance**: Without pre-filtering, vector searches scan entire database
3. **Pipeline coupling**: Database schema must be updated whenever analytics pipeline adds new capabilities
4. **Backward compatibility**: No mechanism to handle records with different metadata versions

## Decision

We will implement a **2-tier hybrid search architecture** using VDMS schema-less properties:

### Architecture Overview

```
Detection → Metadata Extraction → Vector Generation → Storage
                                       ↓
                              VDMS Descriptor Entry
                         ┌─────────────────────────┐
                         │ Properties (Metadata)   │
                         │ • uuid, type      │
                         │ • make, model           │
                         │ • color (optional)      │
                         │ • license_plate         │
                         │ • confidence_scores     │
                         │ • ANY future fields     │
                         └─────────────────────────┘
                         ┌─────────────────────────┐
                         │ Binary Blob (Vector)    │
                         │ • 256-dim float32 vec   │
                         │ • L2 similarity metric  │
                         └─────────────────────────┘

Query → Extract Vector → Build Constraints → VDMS Search
              ↓                  ↓                 ↓
         256-dim vec      Metadata filters   Find + Rank
                                ↓
                        TIER 1: Database-level
                        metadata filtering
                                ↓
                        TIER 2: L2 distance
                        on filtered candidates
```

### Implementation Details

1. **Schema-less Storage**: Use VDMS properties flexibly
   - No predefined metadata schema
   - Analytics pipeline outputs ANY properties
   - Properties stored as key-value pairs
   - New fields added without migration

2. **2-Tier Search Process**:
   - **TIER 1**: Apply metadata constraints at database level (VDMS constraints)
     - Filters by type, color, make, model, license_plate, etc.
     - Executed inside VDMS before vector search
     - Reduces candidate set significantly
   - **TIER 2**: Vector similarity search on filtered candidates
     - L2 distance on 256-dim embeddings
     - Only processes constrained candidates
     - Returns top-k results with metadata

3. **Dynamic Constraints**: Build constraint expressions at query time
   - Query can specify ANY subset of available metadata fields
   - Missing metadata fields handled gracefully (NULL values)
   - Old records work alongside new records
   - No database migration required

## Implementation Approach

### Phase 1: Initial Implementation (Current)

- Extend VDMS adapter with flexible metadata support
- Build constraints dynamically in query based on input from video analytics service
- Query and storage schema are flexible

#### Pros

- **Schema Flexibility**: Analytics pipeline evolves independently from database
- **No Migrations**: Schema-less nature eliminates data migration burden
- **Performance**: 2-tier filtering provides <1ms response times for queries
- **Backward Compatible**: Old records with fewer attributes work seamlessly
- **Industry Standard**: 2-tier approach widely used in production. Especially at the edge.
- **Operational Simplicity**: No schema management overhead
- **Future-Proof**: Can adapt to unforeseen metadata requirements

#### Cons

- **Limited Constraint Types**: VDMS supports only exact-match constraints (==)
  - No range queries (e.g., confidence > 0.9)
  - No substring queries (e.g., plate contains "ABC")
  - Mitigation: Application-level post-filtering if needed
- **No Semantic Matching**: Metadata filtering is exact, not fuzzy
  - "red" ≠ "crimson" in constraints
  - Mitigation: Pre-normalize metadata values when choosing models
- **Storage of NULLs**: Optional metadata stored as empty strings
  - Slight overhead for unused fields
  - Mitigation: Acceptable trade-off for flexibility
- **VDMS dependency**: Phase1 implementation is simplified by schema-less attribute storage support by VDMS. Extending the implementation to be Vector DB agnostic will require additional effort.

### Phase 2: Confidence Scores, Voting and Versioning

- Store confidence metrics with detections. Both from model and from voting over time.
- Statically and dynamically varying the trust scores for each attribute.
- Support versioning. Provenance of stored metadata and embeddings.
- Explore ranking/weighting (not for filtering)

### Phase 3: Spatio-Temporal Tracking

Enable position-aware and time-aware queries for multi-camera tracking:

**Spatial Attributes**:

- **Position**: (x, y, z) coordinates in world space or camera space
- **Orientation**: Heading/yaw angle (0-360 degrees)
- **Velocity**: (vx, vy, vz) motion vector in world coordinates
- **Size**: size of the object bounding box in 3D

**Temporal Context**:

- **Timestamp**: Detection time (epoch seconds or ISO 8601)

**Query Capabilities**:

- **Spatial radius queries**: Find objects within distance R from position (x, y, z)
  - Use case: "Find vehicles within 50m of this location"
  - Implementation: Store position as discrete attributes, compute distance in application layer
- **Temporal range queries**: Find detections within time window [t_start, t_end]
  - Use case: "Find objects detected in last 5 minutes"
  - Implementation: Constraint-based filtering with timestamp ranges
- **Trajectory reconstruction**: Link detections across cameras using position + time + velocity
  - Use case: Spatio-temporally aware Re-ID in multi-camera systems
  - Implementation: Post-process similar Re-ID matches by temporal/spatial consistency

**Benefits**:

- Eliminates false positives that are not spatio-temporally consistent
- Leverages camera calibration data for consistent world coordinates

## Alternatives Considered

### Alternative 1: Vector Concatenation

Embed metadata into extended vector using language models:

**Pros**:

- Single unified vector for similarity
- Metadata affects distance calculation naturally

**Cons**:

- 50-500ms overhead per embedding (language model inference)
- Model versioning issues (incompatible vectors between versions)
- Semantic drift (unintended matches due to embedding similarity)
- Storage bloat (2.5x larger vectors)
- Opaque debugging (why did this match?)
- ❌ Not suitable for real-time tracking

### Alternative 2: Milvus Native Hybrid Search

Use Milvus `search()` with expression filtering:

**Pros**:

- Native database support for hybrid search
- Clean API for expressions
- Good scalability

**Cons**:

- Requires predefined schema upfront
- Schema changes require data migration for all records
- Rigid (must know all metadata fields in advance)
- ❌ Incompatible with evolving analytics pipeline

### Alternative 3: Dual-Index Strategy

Separate indices for metadata and vectors:

**Pros**:

- Highly scalable
- Each index optimized for its data type
- Potential GPU acceleration

**Cons**:

- High operational complexity
- Difficult to maintain consistency
- Only justified for 100M+ objects
- ❌ Overengineered for current scale

### Alternative 4: ML Reranking (Application-Level)

Post-process vector search results using trained ML model:

**Approach**:

1. Vector search returns top-k candidates (vector similarity only)
2. ML reranker model considers metadata + vectors
3. Rerank candidates using model predictions
4. Return top results after reranking

**Pros**:

- Flexible metadata consideration (semantic matching possible)
- Can weight metadata and vector similarity independently
- Supports complex interaction patterns
- Good for research/exploration

**Cons**:

- 50-200ms inference overhead per query (model inference cost)
- Requires training data for reranker model
- Model versioning complexity (old vs new ranking behavior)
- Still doesn't solve schema flexibility (metadata schema still needed upfront)
- Adds operational burden (model retraining, A/B testing)
- Metadata filtering still happens at application level (slower than database)
- Scalability limited by model inference throughput
- ❌ More suitable for ranking refinement than core architecture

### Why VDMS 2-Tier is Optimal

| Criterion             | VDMS 2-Tier    | Concat      | Milvus      | Dual-Index | ML Rerank    |
| --------------------- | -------------- | ----------- | ----------- | ---------- | ------------ |
| **Flexibility**       | ✅ Excellent   | ❌ Poor     | ❌ Rigid    | ✅ Good    | ✅ Excellent |
| **Performance**       | ✅ <1ms filter | ❌ 50-500ms | ✅ Fast     | ✅ Fast    | ❌ 50-200ms  |
| **No Migration**      | ✅ Schema-less | ✅ Yes      | ❌ Requires | ✅ Yes     | ⚠️ Partial   |
| **Pipeline-Agnostic** | ✅ Yes         | ❌ No       | ❌ No       | ✅ Yes     | ⚠️ With work |
| **Debugging**         | ✅ Clear       | ❌ Opaque   | ✅ Clear    | ✅ Clear   | ⚠️ Opaque    |
| **Scalability**       | ✅ 10M-100M    | ✅ 1M-10M   | ✅ 10M-100M | ✅ 100M+   | ⚠️ 100K-1M   |
| **Complexity**        | ✅ Low         | ✅ Low      | ⚠️ Medium   | ❌ High    | ❌ High      |
| **Ops Burden**        | ✅ None        | ✅ None     | ⚠️ Schema   | ❌ Index   | ❌ Model     |

## References

- VDMS Documentation: [Intel VDMS GitHub](https://github.com/IntelLabs/vdms)
- Architecture: Inspired by Apache Solr, Elasticsearch hybrid search approaches
