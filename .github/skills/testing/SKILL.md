---
name: testing
description: >-
  Create or modify Scenescape pytest cases (unit, functional, integration, UI, BAT)
  with SCENESCAPE_SPEC, Zephyr IDs, and positive/negative coverage. Use when adding
  or modifying tests under tests/, or choosing unit vs functional vs UI. Not for
  running/diagnosing tests (test-verification-gate) or lint/format/license-only edits.
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Creating Test Cases for Scenescape

## Test philosophy

- Always add **positive** and **negative** cases (valid path + invalid/edge/boundary).
- Keep tests independent: own setup/teardown; no order dependence.
- Unit tests mock external deps; functional/UI use live services via fixtures.

## Runtime verification (mandatory)

After creating or modifying tests, follow
[`.github/skills/test-verification-gate/SKILL.md`](../test-verification-gate/SKILL.md)
for target selection, image freshness, execution, and pass/fail reporting.
Do not treat lint or syntax checks as verification.

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

| Category | Location | When | Infrastructure | Read |
| --- | --- | --- | --- | --- |
| Unit | `tests/sscape_tests/` or service `*/tests/` | Isolated functions/classes; no live services | Mocks; host pytest | [unit-tests.md](references/unit-tests.md) |
| Functional | `tests/functional/` | Workflows with live REST/MQTT/DB | `SCENESCAPE_SPEC` + `scenescape_env` | [functional-tests.md](references/functional-tests.md) |
| Integration | `tests/functional/` or `tests/system/` | Cross-service pipelines | Same as functional | [functional-tests.md](references/functional-tests.md) |
| UI | `tests/ui/` | Browser/Selenium flows | `SCENESCAPE_SPEC` + `AUTH_BROWSER` | [ui-and-bat-tests.md](references/ui-and-bat-tests.md) |
| Non-functional | `tests/non_functional/` | Performance, build size/time, API contract | `scenescape_env` + `result_recorder` | [functional-tests.md](references/functional-tests.md) |
| BAT | functional/UI + `@pytest.mark.basic_acceptance` | Critical-path smoke | Same as parent category | [ui-and-bat-tests.md](references/ui-and-bat-tests.md) |

Read only the reference for your category; load the rest only if needed:
[conftest-and-zephyr.md](references/conftest-and-zephyr.md) (fixtures, markers, Zephyr IDs),
[running-tests.md](references/running-tests.md) (make targets, backends, log flags),
[multi-controller hierarchy fixtures](references/functional-tests.md#multi-controller-hierarchy-fixtures).

## Hard requirements

### Zephyr IDs (`@pytest.mark.test_name`) — CI source of truth

CI enforces this via `make check-zephyr-ids` → `tests/scripts/check_zephyr_mapping.py`.
That check **excludes** `tests/sscape_tests/` and fails on missing / invalid / duplicate
`NEX-T#####` markers for every other collected test.

| Category | `@pytest.mark.test_name("NEX-T#####")` |
| -------- | ------------------------------------- |
| Unit (`tests/sscape_tests/`, service `*/tests/`) | **Do not add.** CI does not require or check it. |
| Functional, integration, UI, non_functional, BAT, perf | **Required** — unique per test method |

- **Non-unit**: every test method needs its own unique `NEX-T#####`, plus `result_recorder`
  using that same ID. Never share one NEX ID across multiple test methods in a module.
- **Unit (mandatory agent rule)**: **never** add `@pytest.mark.test_name(...)`,
  `TEST_NAME = "NEX-T…"`, or copy a sibling UI/functional Zephyr ID onto unit cases.
  Existing unit files that omit markers are correct; do not “fix” them by adding IDs.
- Details: [Conftest and Zephyr](references/conftest-and-zephyr.md).

### Other requirements

- **Functional/UI**: declare module-level `SCENESCAPE_SPEC = FuncTestSpec(...)` with the correct `ServiceProfile` from `tests/utils/profiles.py`.
- **Naming**: files `test_*.py`, functions `test_*` (pytest norms).
- **Markers that matter**:
  - `@pytest.mark.basic_acceptance` — BAT / `make run_basic_acceptance_tests`
  - `@pytest.mark.kubernetes_only` — skipped on `--backend=docker`
- **Isolation**: Create test data with the `scene_factory` fixture (auto-removes its scenes/cameras on teardown)
  and clean up anything else the test mutates.

## Authoring checklist

Before marking a test-authoring task complete:

- [ ] Non-unit tests: unique Zephyr ID on every test method; unit tests: **no** `test_name` / NEX-T markers
- [ ] Positive and negative (or boundary) cases; at least one negative unless N/A
- [ ] Correct category location and markers
- [ ] Functional/UI declare `SCENESCAPE_SPEC`
- [ ] Unit tests mock externals; functional/UI use real stack data
- [ ] Independent setup/teardown; clear docstrings
- [ ] Import-path policy followed (conftest checked; no stray `sys.path.insert`)
- [ ] Runtime verification done per test-verification-gate (or blocker reported)

Automated eval cases: [evals/evals.json](evals/evals.json).
