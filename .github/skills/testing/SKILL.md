---
name: testing
description: >-
  Create, run, and diagnose Scenescape pytest cases (unit, functional, integration,
  UI, BAT) with SCENESCAPE_SPEC, Zephyr IDs, and positive/negative coverage.
  MANDATORY before modifying any file under tests/, writing pytest, running tests, or
  diagnosing a failing test, test-job CI failure, or test regression. Load only the
  reference matching the test category, and use test-verification-gate when runtime
  verification is needed. Not for formatting/lint/license-only CI failures or
  mechanical edits with no behavioral impact (license year, comment typo).
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing in Scenescape

## Scope

Triggers are in the frontmatter `description`. Do not load this skill or its references for
formatting, lint, indentation, or license-header CI failures where no test fails (use the
matching language/Makefile skill, e.g. `make indent-check`, `make prettier-check`).

## Load only what the task needs

Read this file, then **only the one reference** that matches the test category or activity.
Do not load every reference.

| Task (author or diagnose)                        | Read                                                        |
| ------------------------------------------------ | ----------------------------------------------------------- |
| Unit test                                        | [unit-tests.md](references/unit-tests.md)                   |
| Functional, integration, or non-functional test  | [functional-tests.md](references/functional-tests.md)       |
| UI or BAT test                                   | [ui-and-bat-tests.md](references/ui-and-bat-tests.md)       |
| Fixtures, markers, Zephyr IDs                    | [conftest-and-zephyr.md](references/conftest-and-zephyr.md) |
| Running tests, make targets, backends, log flags | [running-tests.md](references/running-tests.md)             |

Multi-controller hierarchy fixtures:
[functional-tests.md](references/functional-tests.md#multi-controller-hierarchy-fixtures).

## Test philosophy

- Always add **positive** and **negative** cases (valid path + invalid/edge/boundary).
- Keep tests independent: own setup/teardown; no order dependence.
- Unit tests mock external deps; functional/UI use live services via fixtures.

## Runtime verification (mandatory)

When runtime verification is needed (after creating or modifying tests, or when re-running tests to
diagnose a failure), follow
[`.github/skills/test-verification-gate/SKILL.md`](../test-verification-gate/SKILL.md)
for target selection, image freshness, execution, and pass/fail reporting.
Do not treat lint or syntax checks as verification.

## Diagnosing a failing test

1. Classify the failing test by path and read only that category's reference (plus `running-tests.md` for invocation and log flags).
2. Re-run the narrowest pytest invocation that reproduces it, following the verification gate (confirm image freshness before code-level debugging).
3. Inspect per-test logs under `tests/.test_logs/<group>/<test_id>/` (container logs for failures are in the `...-containers/` sibling).
4. Report the exact command, the root cause, and the pass/fail result (or the blocker).

## Import path policy (mandatory)

Before adding imports or path setup in a new or modified test file:

1. Check `tests/conftest.py` and the nearest local `conftest.py`.
2. Confirm whether modules are already importable via existing fixtures/path setup.
3. Use direct imports (e.g. `from controller...`) when shared bootstrap already sets paths.
4. Add path manipulation only if no shared bootstrap exists.
5. If required, put setup once in the nearest `conftest.py` — not per test module.

**Prohibited**: `sys.path.insert(...)` in individual test modules when equivalent setup can live in shared `conftest.py`.

**Authoring report**: state whether conftest files were checked, where import-path setup lives, and that no unnecessary per-file `sys.path.insert` was added.

## Category routing

| Category    | Location                                        | When                                         | Infrastructure                       |
| ----------- | ----------------------------------------------- | -------------------------------------------- | ------------------------------------ |
| Unit        | `tests/sscape_tests/` or service `*/tests/`     | Isolated functions/classes; no live services | Mocks; host pytest                   |
| Functional  | `tests/functional/`                             | Workflows with live REST/MQTT/DB             | `SCENESCAPE_SPEC` + `scenescape_env` |
| Integration | `tests/functional/` or `tests/system/`          | Cross-service pipelines                      | Same as functional                   |
| UI          | `tests/ui/`                                     | Browser/Selenium flows                       | `SCENESCAPE_SPEC` + `AUTH_BROWSER`   |
| Non-functional | `tests/non_functional/`                      | Performance, build size/time, API contract   | `scenescape_env` + `result_recorder`  |
| BAT         | functional/UI + `@pytest.mark.basic_acceptance` | Critical-path smoke                          | Same as parent category              |

Read only the matching reference from [Load only what the task needs](#load-only-what-the-task-needs) before writing a category.

## Hard requirements

- **Zephyr ID**: required for every category **except unit tests** (functional, integration, UI, non_functional, BAT) - every **test method** needs its own unique `NEX-T#####` via `@pytest.mark.test_name("NEX-T#####")`, plus `result_recorder` use inside that method referencing the same ID. Never share one NEX ID across multiple test methods in a module.
- **Unit tests**: `NEX-T#####` is **not required**. Mocked, host-only tests under `tests/sscape_tests/` or service `*/tests/` trees may omit `@pytest.mark.test_name(...)` entirely.
- **Functional/UI**: declare module-level `SCENESCAPE_SPEC = FuncTestSpec(...)` with the correct `ServiceProfile` from `tests/utils/profiles.py`.
- **Naming**: files `test_*.py`, functions `test_*` (pytest norms).
- **Markers that matter**:
  - `@pytest.mark.basic_acceptance` — BAT / `make run_basic_acceptance_tests`
  - `@pytest.mark.preserve_db` — skip automatic DB restore
  - `@pytest.mark.kubernetes_only` — skipped on `--backend=docker`

## Authoring checklist

Before marking a test-authoring task complete:

- [ ] Unique Zephyr ID present on every test method (all categories except unit)
- [ ] Positive and negative (or boundary) cases; at least one negative unless N/A
- [ ] Correct category location and markers
- [ ] Functional/UI declare `SCENESCAPE_SPEC`
- [ ] Unit tests mock externals; functional/UI use real stack data
- [ ] Independent setup/teardown; clear docstrings
- [ ] Import-path policy followed (conftest checked; no stray `sys.path.insert`)
- [ ] Runtime verification done per test-verification-gate (or blocker reported)

Automated eval cases: [evals/evals.json](evals/evals.json).
