<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Unit Tests

**Location**: `tests/sscape_tests/<module>/` or service trees (`mapping/tests/`, `autocalibration/tests/`)

**Rules**:

- Fast, no Docker / MQTT / REST / DB
- Mock external dependencies
- Prefer fixtures in the nearest `conftest.py`
- Real examples: `tests/sscape_tests/geometry/`, `tests/sscape_tests/schema/`
- **No Zephyr IDs**: do **not** add `@pytest.mark.test_name("NEX-T#####")` or
  `TEST_NAME = "NEX-T…"`. `make check-zephyr-ids` ignores `tests/sscape_tests/`
  and does not enforce markers here. Do not copy IDs from related UI/functional tests.

## Minimal pattern

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import Mock

import scene_common.geometry as geometry

class TestPoint:
  def test_point_creation_2d(self):
    point = geometry.Point(4.0, 6.0)
    assert point.x == 4.0
    assert point.y == 6.0
    assert not point.is3D

  def test_point_creation_invalid(self):
    with pytest.raises(TypeError):
      geometry.Point(None, None)

def test_external_client_mocked():
  client = Mock()
  client.get.return_value = {"status": "ok"}
  assert client.get("/health")["status"] == "ok"
  client.get.assert_called_once_with("/health")
```

Mock external I/O (MQTT, REST, OpenCV, DB). Prefer fixtures in the nearest `conftest.py`.
No `test_name` marker in the example — that is intentional for unit tests.
