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

## CI check (`make check-zephyr-ids`)

`tests/scripts/check_zephyr_mapping.py` collects every pytest under `tests/` **except**
`tests/sscape_tests/` and fails on:

- `missing_id` — no `@pytest.mark.test_name("NEX-T#####")`
- `invalid_id` — value not matching `NEX-T` + 5–6 digits
- `duplicate_id` — same ID on more than one test

Unit tests are out of scope for this check. Do not add markers there to “satisfy” CI.

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

## Unit tests: do not add Zephyr IDs

Unit tests under `tests/sscape_tests/` (and similar host-only unit trees) must **not**
use `@pytest.mark.test_name(...)` or module-level `TEST_NAME = "NEX-T…"`.

Agents often wrongly copy a related UI/functional `NEX-T#####` onto every unit case
in the same PR — that is incorrect and adds noise. Omit the marker.

Prefer placing shared path/bootstrap setup in the nearest `conftest.py`, not in individual test modules.
