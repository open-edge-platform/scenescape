<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Cluster Analytics - Agent Guide

## Why This Service Exists

- Converts per-object scene detections into higher-level group behavior (clusters, lifecycle, shape, motion patterns).
- Provides downstream consumers a stable, scene-level analytic signal instead of frame-local noise.

## What Matters Most

- Stable cluster identity over time.
- Predictable low-latency per-scene processing.
- Resistance to noisy input without over-fragmenting or over-merging groups.

## Non-Obvious Constraints

- Input is already scene-regulated object data; this service is not a detector.
- One scene tick should produce one coherent analytic publish event for that scene.
- Cluster lifecycle logic is product behavior, not only implementation detail; preserve semantic meaning of state transitions.
- Parameter tuning can change product behavior significantly; avoid silent default changes.

## KPI Targets

| KPI                                               |                            Target | Why                       |
| ------------------------------------------------- | --------------------------------: | ------------------------- |
| Analytics processing latency per scene tick (p95) |                          <= 80 ms | Real-time usability       |
| Cluster ID churn rate                             | <= 2% per minute in steady scenes | Behavioral continuity     |
| False split/merge rate                            |      <= 3% on validation datasets | Decision quality          |
| Publish success rate                              |                          >= 99.9% | Data pipeline reliability |
| CPU utilization at nominal load                   |    <= 1 core avg per active scene | Deployment efficiency     |

## Change Guidance

- Keep clustering output schema and semantics backward compatible unless explicitly versioned.
- Prefer algorithmic changes that are category-aware and test-backed.
- Guard against accidental O(n^2) growth in hot paths.
- For new behavior labels or state transitions, include migration notes for consumers.

## When Editing This Service

- Validate behavior with both sparse and dense scenes.
- Verify stability under temporary object dropout and reappearance.
- Confirm publish behavior remains single-batch per scene update.

## Verification Gate (Standardized)

| Change class                  | Command path                                                                                                                                                                                                                                                           | Pass criteria                                                                                |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| API/schema contracts          | `make cluster_analytics && make -C cluster_analytics test-build && http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests unit-tests` | Exit code 0; no new publish-contract/schema regressions in test output.                      |
| Algorithm/lifecycle logic     | `make cluster_analytics && make -C cluster_analytics test-build && http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests unit-tests` | Exit code 0; no regressions in stability-oriented checks and scene processing behavior.      |
| Performance-sensitive changes | `http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests metrics`                                                                      | Exit code 0; include before/after latency and cluster ID churn measurements for tuned logic. |
| Migrations/persistence        | N/A for this service                                                                                                                                                                                                                                                   | Must be explicitly marked N/A in the PR when no persistent-schema surface is changed.        |
