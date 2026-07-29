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

## Unit-test Zephyr hooks (when using a local conftest)

All tests need a Zephyr ID (`NEX-T#####`). Functional/UI tests typically set it via @pytest.mark.test_name("NEX-T#####"). For unit suites that still use session hooks:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import tests.common_test_utils as common

TEST_NAME = "NEX-T#####"

def pytest_sessionstart():
  print(f"Executing: {TEST_NAME}")

def pytest_sessionfinish(exitstatus):
  common.record_test_result(TEST_NAME, exitstatus)
```

Prefer placing shared path/bootstrap setup in the nearest `conftest.py`, not in individual test modules.
