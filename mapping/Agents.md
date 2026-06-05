<!--
SPDX-License-Identifier: Apache-2.0
(C) 2026 Intel Corporation
-->

# Mapping - Agent Guide

## Why This Service Exists

- Provides experimental 3D reconstruction and localization capabilities to augment SceneScape spatial understanding.
- Converts visual input into map artifacts and queryable spatial outputs for higher-level workflows.

## What Matters Most

- Quality of reconstruction/localization outputs.
- Predictable behavior under heavy compute workloads.
- Safe degradation on constrained hardware.

## Non-Obvious Constraints

- This service is experimental and model-driven; behavior can vary by selected model/runtime.
- Inference and reconstruction are long-running operations; request handling must not assume instant completion.
- Resource pressure (RAM/VRAM/CPU) is a first-order reliability risk.
- Output artifact compatibility matters for downstream consumers more than internal representation.

## KPI Targets

| KPI                                               |                         Target | Why              |
| ------------------------------------------------- | -----------------------------: | ---------------- |
| Reconstruction request acceptance-to-result (p95) | <= 120 s on reference workload | Usable async UX  |
| Localization success rate on valid maps           |                         >= 95% | Functional value |
| Peak memory under nominal job                     |     within deployment envelope | Stability        |
| Failed job rate due to service fault              |                           < 2% | Reliability      |
| Health endpoint availability                      |                       >= 99.9% | Operability      |

## Change Guidance

- Keep async job semantics and status visibility clear and stable.
- Avoid hidden coupling between model-specific code and shared API contract.
- Any preprocessing or postprocessing changes need measurable quality impact evidence.
- Preserve fallback behavior for non-accelerated environments when supported.

## When Editing This Service

- Validate both success and failure paths for long-running jobs.
- Confirm artifact outputs remain consumable by current platform workflows.
- Test representative workloads for timeout/resource regressions.

## Verification Gate (Standardized)

Prerequisite: prepare test images/secrets before running the commands below, for example `SUPASS=<password> make setup_tests`. If your environment requires a proxy, export standard `HTTP_PROXY` / `HTTPS_PROXY` variables in your shell before running these commands rather than editing the command lines below.

| Change class                           | Command path                                           | Pass criteria                                                                                      |
| -------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| API/schema contracts                   | `make mapping && make -C mapping test-build && make -C tests mapping-unit` | Exit code 0; no new API contract/schema regressions in mapping test output.                        |
| Reconstruction/localization logic      | `make mapping && make -C mapping test-build && make -C tests mapping-unit` | Exit code 0; logic tests pass for both success and failure paths.                                  |
| Performance/resource-sensitive changes | `make -C tests mapping-unit`                           | Exit code 0; include before/after runtime and memory-envelope impact for representative workloads. |
| Migrations/persistence                 | N/A for this service                                   | Must be explicitly marked N/A in the PR when only runtime mapping behavior is changed.             |
