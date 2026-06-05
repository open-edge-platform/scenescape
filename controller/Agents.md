<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Scene Controller - Agent Guide

## Why This Service Exists

- Acts as the runtime source of truth for scene state, camera transforms, and tracked objects.
- Fuses incoming platform data into coherent real-time world-state updates for the rest of SceneScape.

## What Matters Most

- Latency and determinism in the ingest-to-track path.
- Track continuity and identity correctness.
- Runtime resilience under bursty message load.

## Non-Obvious Constraints

- This service owns runtime state, not long-term persistence.
- Timestamp handling and ordering behavior are core correctness concerns; do not treat as logging-only details.
- Analytics-only mode is a product mode with different assumptions; preserve mode isolation.
- Schema validation at trust boundaries is mandatory and part of service safety.

## KPI Targets

| KPI                                                   |                        Target | Why                           |
| ----------------------------------------------------- | ----------------------------: | ----------------------------- |
| Message handler latency (p95)                         |                      <= 50 ms | Real-time tracking quality    |
| Ingest-to-publish tracking latency (p95)              |                     <= 120 ms | User-perceived responsiveness |
| Track ID switch rate                                  |  <= 1% on benchmark sequences | Tracking integrity            |
| Message validation failure due to internal regression |                             0 | Contract stability            |
| Sustained processing under nominal load               | no backlog growth over 30 min | Operational stability         |

## Change Guidance

- Prefer backward-compatible schema and payload behavior.
- Any change in association logic, timing policy, or coordinate transform behavior requires explicit benchmark evidence.
- Avoid introducing blocking operations in hot message paths.
- Keep observability points intact for latency and failure triage.

## When Editing This Service

- If tracking logic changes, validate continuity metrics and failure modes (occlusion, dropout, re-entry).
- If time handling changes, test stale/future timestamp behavior and rewrite policies.
- If mode logic changes, test both default and analytics-only execution paths.

## Verification Gate (Standardized)

Containerized test targets such as `logic-unit-tests` and `scene-unit` generally assume test images and secrets have already been prepared, for example with `SUPASS=<password> make setup_tests`. If your environment requires a proxy, rely on your existing `HTTP_PROXY`/`HTTPS_PROXY` environment variables rather than hard-coding proxy values in the command line.

| Change class                    | Command path                                                                                                             | Pass criteria                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| API/schema contracts            | `SUPASS=<password> make setup_tests && make controller && make -C controller test-build && make -C tests logic-unit-tests` | Exit code 0; no new schema validation or payload contract failures.                            |
| Tracking/association/time logic | `SUPASS=<password> make setup_tests && make controller && make -C controller test-build && make -C tests scene-unit`       | Exit code 0; continuity/time-handling checks pass with no new logic regressions.               |
| Performance-sensitive changes   | `make -C tests metrics`                                                                                                    | Exit code 0; include before/after p95 handler latency and ingest-to-publish latency in report. |
| Migrations/persistence          | N/A for this service                                                                                                       | Must be explicitly marked N/A in the PR because controller is runtime-state focused.           |
