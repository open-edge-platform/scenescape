---
name: testing
description: >-
  Create Scenescape pytest cases (unit, functional, integration, UI, BAT) with
  SCENESCAPE_SPEC, Zephyr IDs, and positive/negative coverage. Use when adding or
  modifying tests under tests/, writing pytest, or choosing unit vs functional vs UI.
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

| Category    | Location                                        | When                                         | Infrastructure                       |
| ----------- | ----------------------------------------------- | -------------------------------------------- | ------------------------------------ |
| Unit        | `tests/sscape_tests/` or service `*/tests/`     | Isolated functions/classes; no live services | Mocks; host pytest                   |
| Functional  | `tests/functional/`                             | Workflows with live REST/MQTT/DB             | `SCENESCAPE_SPEC` + `scenescape_env` |
| Integration | `tests/functional/` or `tests/system/`          | Cross-service pipelines                      | Same as functional                   |
| UI          | `tests/ui/`                                     | Browser/Selenium flows                       | `SCENESCAPE_SPEC` + `AUTH_BROWSER`   |
| BAT         | functional/UI + `@pytest.mark.basic_acceptance` | Critical-path smoke                          | Same as parent category              |

Read the matching reference under [Additional resources](#additional-resources) before writing a category.

## Hard requirements

- **Zephyr ID**: every test suite/module needs `NEX-T#####` (@pytest.mark.test_name("NEX-T#####")).
- **Functional/UI**: declare module-level `SCENESCAPE_SPEC = FuncTestSpec(...)` with the correct `ServiceProfile` from `tests/utils/profiles.py`.
- **Naming**: files `test_*.py`, functions `test_*` (pytest norms).
- **Markers that matter**:
  - `@pytest.mark.basic_acceptance` — BAT / `make run_basic_acceptance_tests`
  - `@pytest.mark.preserve_db` — skip automatic DB restore
  - `@pytest.mark.kubernetes_only` — skipped on `--backend=docker`

## Authoring checklist

Before marking a test-authoring task complete:

- [ ] Zephyr ID present
- [ ] Positive and negative (or boundary) cases; at least one negative unless N/A
- [ ] Correct category location and markers
- [ ] Functional/UI declare `SCENESCAPE_SPEC`
- [ ] Unit tests mock externals; functional/UI use real stack data
- [ ] Independent setup/teardown; clear docstrings
- [ ] Import-path policy followed (conftest checked; no stray `sys.path.insert`)
- [ ] Runtime verification done per test-verification-gate (or blocker reported)

## Additional resources

- [Unit tests](references/unit-tests.md)
- [Functional and integration tests](references/functional-tests.md)
  (includes [multi-controller hierarchy fixtures](references/functional-tests.md#multi-controller-hierarchy-fixtures))
- [UI and BAT tests](references/ui-and-bat-tests.md)
- [Conftest and Zephyr](references/conftest-and-zephyr.md)
- [Running tests](references/running-tests.md)

Automated eval cases: [evals/evals.json](evals/evals.json).
