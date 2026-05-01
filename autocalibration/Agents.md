<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Auto Camera Calibration - Agent Guide

## Why This Service Exists

- Produces camera calibration (intrinsics and extrinsics) so downstream tracking can reason in world coordinates.
- Supports two operating strategies (AprilTag and markerless) selected per scene configuration.

## What Matters Most

- Calibration quality is more important than raw throughput.
- End-to-end user workflow must remain responsive: registration, calibration trigger, result delivery.
- Safety of scene-level state transitions (avoid conflicting concurrent calibration work).

## Non-Obvious Constraints

- This service is not the system of record for calibration metadata; it computes and hands results back through platform APIs.
- Strategy choice is scene-driven; avoid hard-coding assumptions that only one mode is active.
- Calibration and scene registration run asynchronously; preserve locking/thread-safety behavior when changing flow control.
- Result delivery to clients is event-driven; avoid changes that make consumers depend on polling-only behavior.

## KPI Targets

| KPI                                        |                    Target | Why                          |
| ------------------------------------------ | ------------------------: | ---------------------------- |
| Scene registration completion (p95)        |     depends on scene size | UI responsiveness            |
| Single-camera calibration completion (p95) | <= 2 s after frame submit | Operator workflow speed      |
| Calibration success rate                   |     >= 99% on valid input | Operational reliability      |
| Reprojection error (median)                |                 <= 5.0 px | Tracking accuracy downstream |
| Concurrent calibration conflict rate       |                         0 | State consistency            |

## Change Guidance

- Keep request/response compatibility stable for Manager and UI clients.
- Treat uploaded payloads as untrusted: enforce size, format, and field validation at service boundary.
- If changing calibration math or thresholds, include measurable before/after quality data.
- Keep long-running operations out of request thread paths.
- New request fields threaded into calibration logic must not introduce per-request mutable state that races with concurrent calibration; verify the concurrent calibration conflict rate KPI remains 0.

## When Editing This Service

- If you touch calibration strategy selection or execution flow, verify both AprilTag and markerless paths.
- If you touch API contracts, update service docs and client expectations in the same change; also confirm the off-thread constraint holds (long-running work must stay off request threads) and that new fields are validated at the boundary (size, format, field).
- If you touch concurrency code, explicitly test overlapping scene/camera requests and verify the concurrent calibration conflict rate remains 0.

## Verification Gate (Standardized)

| Change class                          | Command path                                                                                                                                                                                                                                                             | Pass criteria                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| API/schema contracts                  | `make autocalibration && make -C autocalibration test-build && http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests auto-calibration` | Exit code 0; auto-calibration workflow test passes without new contract/schema failures.           |
| Algorithm/concurrency flow            | `make autocalibration && make -C autocalibration test-build && http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests markerless-unit`  | Exit code 0; markerless calibration path passes with no new race/locking regressions.              |
| Performance/quality-sensitive changes | `http_proxy=http://proxy-dmz.intel.com:911 HTTP_PROXY=http://proxy-dmz.intel.com:911 https_proxy=http://proxy-dmz.intel.com:912 HTTPS_PROXY=http://proxy-dmz.intel.com:912 make -C tests auto-calibration`                                                               | Exit code 0; report before/after p95 completion and reprojection-quality deltas for changed logic. |
| Migrations/persistence                | N/A for this service                                                                                                                                                                                                                                                     | Must be explicitly marked N/A in the PR when only runtime calibration behavior is changed.         |
