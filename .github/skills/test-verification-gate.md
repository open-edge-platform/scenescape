<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# AI Agent Skill: Test Verification Gate

Use this skill whenever a task adds or modifies tests.

## Goal

Ensure runtime verification is completed and reported consistently.

## Required Checklist

1. Select a repository Makefile target that covers the modified tests.
2. Prefer a root target when practical (for example, `make run_unit_tests`).
3. Otherwise select the narrowest scoped target in `tests/Makefile`
   (for example, `make -C tests scenescape-unit`).
4. If the selected target runs in a service `...-test` container image,
   rebuild images for changed services before executing tests.
5. Execute the target.
6. If failures occur, confirm image freshness before code-level debugging:
   - Rebuild the impacted service runtime and test images if not rebuilt.
   - Rerun the same target once on fresh images.
7. If still failing, fix and rerun the same target.
8. Report exact command and concise pass/fail summary.

## Image Freshness Mapping (Common)

- Changed `controller/src/**` + `make -C tests scene-unit`:
  - `make controller`
  - `make -C controller test-build`
  - then run `make -C tests scene-unit SUPASS=<password>`

Apply the same pattern to other services: rebuild runtime + test image before
running containerized test targets.

## Blocked Execution Policy

If execution is blocked (missing environment, skipped setup, unavailable
runtime), report:

1. What is blocked.
2. The exact command that should be run once unblocked.
3. Whether task completion is partial.

## Not Sufficient

- Lint success only
- Syntax-only checks
- IDE static errors only
- Repeated reruns against stale container images

These checks are useful but do not replace runtime test execution.
