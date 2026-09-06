<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# UI and BAT Tests

## UI tests

**Location**: `tests/ui/`

**Rules**:

- Selenium via `tests/ui/browser.py` and `tests/ui/common_ui_test_utils.py`
- Declare `SCENESCAPE_SPEC` with `auth=AUTH_BROWSER`
- Pick a profile that includes the UI and any video/demo deps needed

**Real example**: `tests/ui/test_out_of_box.py`

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from tests.utils.spec import FuncTestSpec, AUTH_BROWSER
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  auth=AUTH_BROWSER,
)


@pytest.mark.basic_acceptance
@pytest.mark.test_name("NEX-T#####")
def test_login_shows_scene_list(scenescape_env, params, result_recorder):
  browser = Browser()
  try:
    common.login(browser, params['weburl'], params['user'], params['password'])
    browser.wait_for_element(By.ID, "scene-list", timeout=10)
    assert browser.find_element(By.ID, "scene-list") is not None

    result_recorder.success()
  finally:
    browser.quit()
```

## BAT (basic acceptance) tests

**Location**: `tests/functional/` or `tests/ui/` with `@pytest.mark.basic_acceptance`

**Run**: `make run_basic_acceptance_tests` or `pytest -m basic_acceptance`

Keep to critical-path sanity checks (service reachable, login works, core MQTT/REST flow).

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from scene_common.rest_client import RESTClient
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

@pytest.mark.basic_acceptance
@pytest.mark.test_name("NEX-T#####")
def test_rest_api_accessible(scenescape_env, params, result_recorder):
  client = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert client.authenticate(params['user'], params['password'])

  result_recorder.success()
```
