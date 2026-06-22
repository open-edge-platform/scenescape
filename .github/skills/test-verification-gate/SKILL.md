---
name: test-verification-gate
description: Runtime test verification gate for Scenescape — image freshness checks, rebuild-before-test requirements, and retry policy.
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# AI Agent Skill: Test Verification Gate

Use this skill whenever a task adds or modifies tests.

## Goal

Ensure runtime verification is completed and reported consistently.

## Required Checklist

1. Identify the changed files and classify scope: unit, functional, ui or perf.
2. Select the narrowest pytest invocation that covers the modified tests:
   - Unit tests (no containers needed): `pytest tests/sscape_tests/<test_file>.py`
   - Functional/UI tests (containers needed): `pytest tests/functional/<test_file>.py`
3. If the test requires running containers and service code changed, rebuild
   the impacted service images before executing tests.
4. Execute the selected command.
5. If failures occur, confirm image freshness before code-level debugging:
   - Rebuild the impacted service runtime image if not rebuilt.
   - Rerun the same command once on fresh images.
6. If still failing, fix and rerun the same command.
7. Report exact command and concise pass/fail summary.

## Image Freshness Mapping (Common)

- Changed `controller/src/**`, testing with `pytest tests/functional/<test>.py`:
  - `make rebuild-controller`
  - then run `pytest tests/functional/<test>.py`

- Changed `manager/src/**`, testing with `pytest tests/functional/<test>.py`:
  - `make rebuild-manager`
  - then run `pytest tests/functional/<test>.py`

Unit tests in `tests/sscape_tests/` run on the host (no container images required).
Apply rebuild only for functional/UI/integration tests that exercise containerized services.

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
