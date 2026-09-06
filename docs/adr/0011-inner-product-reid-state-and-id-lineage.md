<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR 11: Configurable ReID Similarity Metric and Track Lineage Output

- **Author(s)**: Sarat Poluri, GitHub Copilot
- **Date**: 2026-04-22
- **Status**: `Accepted`

## Context

The controller supports choosing the ReID similarity metric via runtime configuration (`reid-config.json`, `similarity_metric`). The configuration default is `COSINE`.

Because VDMS descriptor search uses Inner Product (`IP`) for this flow, the controller maps configured `COSINE` to VDMS `IP` at the database boundary.

The configuration contract allows only `COSINE` and `L2` values. `IP` is an internal VDMS execution detail, not a user-facing config option.

For `IP`, the controller normalizes ReID embedding vectors before storing and querying in VDMS. With normalized vectors, the metric value returned by VDMS is directly interpretable as cosine similarity and is expected to lie in the range `[-1, 1]`.

This matters specifically for **visual embeddings** because most modern ReID models are trained so that identity similarity is expressed primarily through **vector direction**, not vector magnitude. After normalization, the useful signal is the angular agreement between two embeddings. In that setting, Inner Product directly measures the quantity we care about.

For unit-normalized vectors $x$ and $y$:

$$
\lVert x - y \rVert^2 = 2 - 2(x \cdot y)
$$

This means L2 distance and Inner Product induce the same ranking once vectors are normalized. However, they do not provide the same **operational semantics**.

At the same time, downstream consumers need to distinguish between multiple operational states that were previously ambiguous in scene output:

- A track that is still collecting embeddings and has not queried the database yet.
- A track that queried the database and found no match.
- A track that successfully matched a prior identity.
- A track for which ReID has been disabled.

For post-mortem stitching analysis, operators also need more than the current `id` and `similarity` fields. They need a durable per-track history of which global IDs were assigned over time, when each assignment happened, and whether the assignment came from a successful ReID match or from the no-match path.

## Decision

We will make three related changes.

1. Make ReID similarity metric **configurable**, with `COSINE` as the configuration default.
2. Expose explicit **ReID state** on tracked objects so scene output distinguishes query lifecycle from match outcome.
3. Persist and publish a **previous_ids_chain** for each track so identity transitions can be reconstructed after the fact.

### Metric Decision

- Similarity metric is configured at runtime (`similarity_metric`) and propagated into VDMS operations.
- Supported configured metrics are `COSINE` and `L2`.
- Unsupported configured metric values fall back to `COSINE`.
- Configured `COSINE` is translated to VDMS `IP` at the adapter boundary so configuration semantics stay model-friendly while database semantics stay VDMS-compatible.
- For `IP`, ReID vectors are normalized before storage/query and returned values are expected to be finite in `[-1, 1]`.
- For non-`IP` metrics (for example `L2`), vectors are not force-normalized by this controller path, and `[-1, 1]` range validation is not applied.
- Match threshold interpretation is metric-aware:
  - `IP`/similarity-style metrics: higher values are better, match when value > threshold.
  - Distance-style metrics (for example `L2`): lower values are better, match when value < threshold.

### Why Default to `COSINE` (with `IP` in VDMS)

- With normalized embeddings, `IP` is equivalent to cosine similarity, which matches how visual ReID embeddings are typically interpreted.
- L2 and `IP` produce the same neighbor ordering after normalization, but `IP` yields a score where:
  - `1` means identical direction / strongest possible match,
  - `0` means orthogonal / unrelated,
  - `-1` means maximally opposed.
- That bounded and signed score is easier to reason about than L2 distance, where **smaller is better** and the practical range depends on normalization assumptions.
- The controller exposes a `similarity` field and applies a `similarity_threshold`. `COSINE` uses similarity-style (higher-is-better) interpretation by default and is executed via equivalent backend `IP`/DOT operations; `L2` remains available with distance-style semantics.
- `IP` gives a stable contract for downstream systems, logs, tests, and operators: higher is always better, the range is bounded, and invalid values can be rejected with a simple `[-1, 1]` check.
- Because ranking can be equivalent under normalization, configuration still supports `L2` experimentation while `COSINE` provides the default bounded, higher-is-better score contract.

### ReID State Decision

Tracked objects expose a `reid_state` field with these values:

- `pending_collection`: the controller is still collecting quality embeddings and has not completed a database query.
- `query_no_match`: a query was made and no usable database match was selected.
- `matched`: a query produced a valid reusable database identity.
- `reid_disabled`: ReID is disabled and no query will be attempted.

This state is carried on the `MovingObject`, updated by the UUID manager, and emitted in controller output for downstream logic.

### ID Lineage Decision

Each tracked object maintains `previous_ids_chain`, a chronological list of entries shaped as:

```text
{
  "id": <assigned global id>,
  "timestamp": <assignment time>,
  "similarity_score": <match score or null>
}
```

The chain is updated whenever UUID assignment is finalized:

- On a successful ReID match, the matched database ID is appended with the associated similarity score.
- On a no-match outcome, the newly assigned controller-generated ID is appended with `similarity_score = null`.

When serialized in controller output, timestamps are normalized to ISO 8601, and the field is omitted when no assignments have been recorded yet.

## Alternatives Considered

- Keep the previous metric behavior implicit.
  - Rejected because downstream interpretation of `similarity` requires explicit metric semantics.
- Hard-code `IP` and disallow alternatives.
  - Rejected because teams need to evaluate metric choices per model/domain without code changes.
- Emit only `similarity` without an explicit `reid_state`.
  - Rejected because `null` similarity alone cannot distinguish "not queried yet", "no match", and "ReID disabled".
- Emit only the latest assigned ID.
  - Rejected because it prevents post-mortem reconstruction of identity stitching decisions and removes valuable debugging data for false merges or missed matches.
- Store lineage only in logs.
  - Rejected because logs are incomplete as an API contract and are harder for downstream systems and tests to consume deterministically.

## Consequences

### Positive

- Similarity scoring semantics are explicit and metric-aware.
- For the default `IP` path, normalized embeddings plus `IP` yields a bounded score in `[-1, 1]`, and invalid values are rejected early.
- Downstream consumers can branch reliably on `reid_state` instead of inferring intent from `similarity` alone.
- Operators can reconstruct identity evolution for a track using `previous_ids_chain`.
- Unit and functional verification become easier because query lifecycle and assignment outcomes are visible in structured output.

### Negative

- Controller output now carries additional state that downstream consumers must understand and preserve.
- `previous_ids_chain` increases payload size for long-lived tracks.
- Operators must understand that threshold direction depends on metric choice.
- The `IP` safety checks (`[-1, 1]`) are metric-specific and intentionally not applied to non-`IP` metrics.

## References

- `controller/src/controller/vdms_adapter.py`
- `controller/src/controller/uuid_manager.py`
- `controller/src/controller/moving_object.py`
- `controller/src/controller/detections_builder.py`
- `docs/user-guide/microservices/controller/data_formats.md`
