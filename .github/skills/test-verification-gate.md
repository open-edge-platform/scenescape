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
4. Execute the target.
5. If failures occur, fix and rerun the same target.
6. Report exact command and concise pass/fail summary.

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

These checks are useful but do not replace runtime test execution.
