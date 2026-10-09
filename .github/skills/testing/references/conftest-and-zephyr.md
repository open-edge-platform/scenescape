<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Conftest Patterns and Zephyr IDs

## Root `tests/conftest.py`

Owns session lifecycle:

- Session fixtures: `repo_root`, `version`, `secrets_dir`, `supass`, compose manager
- Function fixtures: `scenescape_env`, `params`, `result_recorder`
- Hooks: profile-ordered collection, CLI options, per-test logging / container log collection
- Zephyr ID handling:
  - `@pytest.mark.test_name("NEX-T#####")` sets the XML test name
  - `result_recorder` prints `NEX-T#####: PASS` or `NEX-T#####: FAIL` on teardown
  - If `result_recorder.success()` is never reached, the result defaults to `FAIL`

## Functional `tests/functional/conftest.py`

Adds functional helpers (`rest`, `scene_uid`, etc.) and related setup fixtures.

## Zephyr IDs: every category except unit tests

Required for any test that isn't a unit test. Each test method must carry its own
unique `NEX-T#####` and pass that same ID into `result_recorder`:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

@pytest.mark.test_name("NEX-T10001")
def test_foo(result_recorder):
  ...
  result_recorder.success()

@pytest.mark.test_name("NEX-T10002")
def test_bar(result_recorder):
  ...
  result_recorder.success()
```

## Unit tests: no Zephyr ID required

Unit tests (`tests/sscape_tests/`) do not need a Zephyr ID.

Prefer placing shared path/bootstrap setup in the nearest `conftest.py`, not in individual test modules.
