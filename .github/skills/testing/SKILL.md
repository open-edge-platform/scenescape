---
name: testing
description: Guide for creating Scenescape test cases — unit, functional, integration, UI, and smoke tests with positive and negative cases.
---

# AI Agent Guide: Creating Test Cases for Scenescape

This guide provides comprehensive instructions for AI agents to create high-quality, well-categorized test cases for the Scenescape project.

## Test Philosophy

**Always create BOTH positive and negative test cases:**

- **Positive tests**: Verify expected behavior with valid inputs
- **Negative tests**: Verify proper error handling with invalid inputs, edge cases, and boundary conditions

**Test isolation and independence:**

- Tests should not depend on execution order
- Each test should set up its own data and clean up after itself
- Use mocking to isolate units from external dependencies

## Verification Workflow For AI Agents (Mandatory)

Use `.github/skills/test-verification-gate/SKILL.md` for runtime verification,
command selection, and completion reporting rules after creating or modifying
tests.

## Test Import Path Policy (Mandatory)

Before adding imports or path setup in any new or modified test file, run this
discovery workflow:

1. Check shared pytest bootstrap files first:
   - `tests/conftest.py`
   - nearest local `conftest.py` in the target test directory tree
2. Verify whether the required modules are already importable via existing
   fixtures/path setup.
3. Use direct imports (for example `from controller...`) when existing
   `conftest.py` already establishes paths.
4. Only add path manipulation if no appropriate shared bootstrap exists.
5. If path setup is genuinely required, prefer adding it once in the nearest
   relevant `conftest.py` rather than per-test-file setup.

### Prohibited Pattern

- Do not add `sys.path.insert(...)` blocks in individual test modules when
  equivalent setup can live in shared `conftest.py`.

### Completion Check For Test Authoring

When creating or updating tests, report this explicitly:

- whether `conftest.py` files were checked
- where import-path setup is defined (file path)
- confirmation that no unnecessary per-file `sys.path.insert` was introduced

## Test Target Mapping Workflow (Mandatory)

Run this workflow before executing any test command:

1. Identify changed files.
2. Classify each changed file scope: unit, functional, ui, perf, or integration.
3. Resolve the concrete target from the `Makefile` test targets.
4. Choose the narrowest target that directly validates the changed file(s).
5. Run that target with required environment variables.

### Anti-Miss Checklist

- Do not treat unit target success as validation for functional test changes.
- Do not run broad aggregate targets unless no narrow target exists or the user explicitly requests a sweep.
- Do not report completion without runtime verification for the resolved target (unless blocked).
- Always report: should-run target, whether it was run, exact command, and pass/fail summary (or blocker).

### Quick Mapping Examples

- `tests/functional/test_roi_mqtt.py` -> `pytest tests/functional/test_roi_mqtt.py`
- `tests/ui/test_out_of_box.py` -> `pytest tests/ui/test_out_of_box.py`
- `tests/sscape_tests/geometry/test_point.py` -> `pytest tests/sscape_tests/geometry/test_point.py`

## Test Categories

### 1. Unit Tests

**Purpose**: Test individual functions, methods, or classes in isolation

**Location**: `tests/sscape_tests/<module>/` or within service directories (`mapping/tests/`, `autocalibration/tests/`)

**Characteristics**:

- Fast execution (< 1 second per test)
- No external dependencies (databases, MQTT, REST APIs)
- Use mocking for all external calls
- Test single units of functionality

**When to create unit tests**:

- Testing utility functions (geometry calculations, data transformations)
- Testing class methods with clear inputs/outputs
- Testing data validation logic
- Testing schema validation
- Testing algorithm implementations

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import Mock, patch, MagicMock

import scene_common.geometry as geometry

class TestPointClass:
    """Test suite for geometry.Point class"""

    # Positive tests
    def test_point_creation_2d_cartesian(self):
        """Test creating a 2D point with cartesian coordinates"""
        point = geometry.Point(4.0, 6.0)

        assert point.x == 4.0
        assert point.y == 6.0
        assert not point.is3D

    def test_point_creation_3d_cartesian(self):
        """Test creating a 3D point with cartesian coordinates"""
        point = geometry.Point(4.0, 6.0, 8.0)

        assert point.x == 4.0
        assert point.y == 6.0
        assert point.z == 8.0
        assert point.is3D

    # Negative tests
    def test_point_creation_invalid_coordinates(self):
        """Test that Point raises error with invalid coordinates"""
        with pytest.raises(TypeError):
            geometry.Point(None, None)

    def test_point_creation_mixed_types(self):
        """Test that Point raises error with mixed valid/invalid types"""
        with pytest.raises(TypeError):
            geometry.Point(4.0, "invalid")

    # Boundary tests
    def test_point_with_zero_coordinates(self):
        """Test point creation at origin"""
        point = geometry.Point(0.0, 0.0)

        assert point.x == 0.0
        assert point.y == 0.0

    def test_point_with_negative_coordinates(self):
        """Test point creation with negative values"""
        point = geometry.Point(-10.0, -20.0)

        assert point.x == -10.0
        assert point.y == -20.0

    # Parametrized tests for multiple cases
    @pytest.mark.parametrize("x,y,z,expected_3d", [
        (1.0, 2.0, None, False),
        (1.0, 2.0, 3.0, True),
        (0.0, 0.0, 0.0, True),
        (-5.0, -10.0, -15.0, True),
    ])
    def test_point_dimensionality(self, x, y, z, expected_3d):
        """Test that point correctly identifies 2D vs 3D"""
        if z is None:
            point = geometry.Point(x, y)
        else:
            point = geometry.Point(x, y, z)

        assert point.is3D == expected_3d
```

**Mocking examples**:

```python
from unittest.mock import Mock, patch, MagicMock

class TestCameraCalibration:
    """Test camera calibration with mocked OpenCV"""

    @patch('cv2.solvePnP')
    def test_calibration_success(self, mock_solve_pnp):
        """Test successful camera calibration with mocked cv2"""
        # Setup mock return value
        mock_solve_pnp.return_value = (
            True,  # success
            np.array([[0.1], [0.2], [0.3]]),  # rvec
            np.array([[1.0], [2.0], [3.0]])   # tvec
        )

        # Run calibration
        result = calibrate_camera(image_points, object_points)

        # Verify
        assert result.success is True
        mock_solve_pnp.assert_called_once()

    @patch('cv2.solvePnP')
    def test_calibration_failure(self, mock_solve_pnp):
        """Test calibration failure handling"""
        # Setup mock to return failure
        mock_solve_pnp.return_value = (False, None, None)

        # Run and verify error handling
        with pytest.raises(CalibrationError):
            calibrate_camera(image_points, object_points)

class TestMQTTPublisher:
    """Test MQTT publishing with mocked PubSub"""

    def test_publish_detection_message(self):
        """Test publishing detection with mocked MQTT"""
        # Create mock PubSub
        mock_pubsub = Mock()
        mock_pubsub.publish = Mock()

        # Create publisher with mock
        publisher = DetectionPublisher(mock_pubsub)
        detection = {"id": "cam1", "objects": []}

        # Publish
        publisher.publish_detection(detection)

        # Verify publish was called with correct topic and data
        mock_pubsub.publish.assert_called_once()
        args = mock_pubsub.publish.call_args
        assert "detection" in args[0][0]  # Topic contains 'detection'
```

**Pytest fixtures for unit tests**:

```python
# In conftest.py
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_rest_client():
    """Mock REST client for unit tests"""
    client = Mock()
    client.get = Mock(return_value={"status": "ok"})
    client.post = Mock(return_value={"id": "123"})
    return client

@pytest.fixture
def sample_image_data():
    """Provide sample image data for tests"""
    return np.zeros((100, 100, 3), dtype=np.uint8)

@pytest.fixture
def sample_detection():
    """Provide sample detection data"""
    return {
        "id": "camera1",
        "timestamp": "2025-01-06T12:00:00.000Z",
        "objects": {
            "person": [{
                "id": 1,
                "category": "person",
                "bounding_box": {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2}
            }]
        }
    }
```

### 2. Functional Tests

**Purpose**: Test complete workflows and interactions between components with live services

**Location**: `tests/functional/`

**Characteristics**:

- Docker Compose lifecycle managed automatically by pytest fixtures (`scenescape_env`)
- Tests declare required services via module-level `SCENESCAPE_SPEC` using `FuncTestSpec` + `ServiceProfile`
- Database restored automatically after each test (unless `@pytest.mark.preserve_db`)
- Test real interactions between services (REST API, MQTT, database)
- Longer execution time (seconds to minutes)
- Use real data, not mocks
- Test end-to-end scenarios

**When to create functional tests**:

- Testing REST API endpoints with database interactions
- Testing MQTT message flow through the system
- Testing scene controller state management
- Testing camera calibration workflows
- Testing object tracking across multiple frames

**Infrastructure**: The `scenescape_env` fixture in `tests/conftest.py` reads `SCENESCAPE_SPEC` from the test module, starts the required Docker Compose services via `ServiceProfile`, waits for readiness, injects connection parameters into `params`, and restores the database on teardown.

**Available profiles**: Check `tests/utils/profiles.py` for predefined `ServiceProfile` configurations.

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.functional.common_scene_obj import SceneObjectMqtt
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

# Declare required Docker Compose services
SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

# Optional: map profile names to Zephyr IDs for --env-profiles matrix
SCENESCAPE_ENV_MATRIX = {
  "full_stack": "NEX-T10404",
}

TEST_NAME = "NEX-T10404"


@pytest.mark.basic_acceptance
def test_roi_create(scenescape_env, demo_scene, request, record_xml_attribute):
  """Test ROI creation via MQTT.

  Requesting scenescape_env triggers Docker Compose startup with FULL_STACK
  profile. The params fixture provides broker_url, resturl, auth, etc.
  """
  test_name = getattr(request.node, '_scenescape_test_name', TEST_NAME)
  test = SceneObjectMqtt(test_name, request, record_xml_attribute)
  runROIMqttCreate(test)
  assert test.exitCode == 0
```

**FuncTestSpec fields**:

```python
from dataclasses import dataclass

@dataclass
class FuncTestSpec:
  profile: object              # ServiceProfile (from tests/utils/profiles.py)
  auth: str = ""              # AUTH_CONTROLLER or AUTH_BROWSER
  require_password: bool = True
  test_name: str = ""         # NEX ID for XML reporting
  extra_args: list = None     # Extra --key value pairs for params
  exampledb: str = ""         # Override baseline DB (e.g., "calibrationdb.tar.bz2")
```

**Multi-profile testing** (via `--env-profiles`):

```bash
# Run test against multiple profiles
pytest tests/functional/test_roi_mqtt.py --env-profiles=full_stack,full_stack_with_mapping
# Generates: test_roi_create[full_stack], test_roi_create[full_stack_with_mapping]
```

**MQTT functional test example**:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import pytest

from scene_common.mqtt import PubSub
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T#####"

def test_detection_produces_tracking(scenescape_env, params, record_xml_attribute):
  """Test that detection message produces tracking output."""
  record_xml_attribute("name", TEST_NAME)

  tracking_data = []

  def on_tracking(client, userdata, message):
    data = json.loads(message.payload.decode('utf-8'))
    tracking_data.append(data)

  pubsub = PubSub(params['auth'], None, params['rootcert'],
                   params['broker_url'], port=int(params['broker_port']))
  pubsub.addCallback("tracking/+", on_tracking)

  detection = {
    "id": "camera1",
    "timestamp": "2026-01-06T12:00:00.000Z",
    "objects": {
      "person": [{"id": 1, "category": "person",
                   "bounding_box": {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2}}]
    }
  }
  pubsub.publish("detection/camera1", json.dumps(detection))

  timeout = 10
  elapsed = 0
  while not tracking_data and elapsed < timeout:
    time.sleep(0.5)
    elapsed += 0.5

  assert tracking_data, "No tracking message received"
  assert 'objects' in tracking_data[0]
```

### 3. Integration Tests

**Purpose**: Test cross-container interactions and service integration with real data

**Location**: `tests/functional/` or `tests/system/`

**Characteristics**:

- Require multiple running containers (managed by `scenescape_env` fixture)
- Test real service-to-service communication
- Use actual databases, message brokers, and services
- Test realistic data flows
- Longer execution times
- Use `SCENESCAPE_SPEC` with appropriate `ServiceProfile` for required services

**When to create integration tests**:

- Testing Scene Controller → Manager → Database flow
- Testing MQTT → Controller → REST API chain
- Testing calibration service with real image data
- Testing mapping service with controller integration
- Testing complete detection → tracking → storage pipeline

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T#####"

def test_complete_detection_tracking_pipeline(scenescape_env, params, record_xml_attribute):
  """Integration test: detection → controller → tracking → database."""
  record_xml_attribute("name", TEST_NAME)

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  tracking_results = []

  def on_tracking(client, userdata, message):
    data = json.loads(message.payload.decode('utf-8'))
    tracking_results.append(data)

  pubsub = PubSub(params['auth'], None, params['rootcert'],
                   params['broker_url'], port=int(params['broker_port']))
  pubsub.addCallback("tracking/+", on_tracking)

  # Publish detection via MQTT
  detection = {
    "id": "camera1",
    "timestamp": "2026-01-06T12:00:00.000Z",
    "objects": {
      "person": [{"id": 1, "category": "person",
                   "bounding_box": {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2}}]
    }
  }
  pubsub.publish("detection/camera1", json.dumps(detection))

  # Wait for tracking output
  timeout = 15
  elapsed = 0
  while not tracking_results and elapsed < timeout:
    time.sleep(0.5)
    elapsed += 0.5

  assert tracking_results, "No tracking output received"
  assert 'objects' in tracking_results[0]
```

### 4. UI Tests

**Purpose**: Test web interface functionality using browser automation

**Location**: `tests/ui/`

**Characteristics**:

- Use Selenium WebDriver (Firefox/geckodriver with Xvfb for headless)
- Docker Compose lifecycle managed by `scenescape_env` fixture via `SCENESCAPE_SPEC`
- Use `AUTH_BROWSER` for web UI authentication
- Test user interactions and workflows
- Verify visual elements and user feedback
- Slower execution

**When to create UI tests**:

- Testing login/authentication flow
- Testing scene creation and management UI
- Testing camera configuration interface
- Testing map visualization features
- Testing form validation and error messages

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.ui.browser import Browser, By
import tests.ui.common_ui_test_utils as common
from scene_common.mqtt import PubSub
from tests.utils.spec import FuncTestSpec, AUTH_BROWSER
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  auth=AUTH_BROWSER,
)

TEST_NAME = "NEX-T#####"

@pytest.mark.basic_acceptance
def test_out_of_box(scenescape_env, params, record_xml_attribute):
  """Test out-of-box experience via web UI."""
  record_xml_attribute("name", TEST_NAME)

  # params contains: user, password, broker_url, weburl, resturl, auth, rootcert
  browser = Browser()
  try:
    common.login(browser, params['weburl'], params['user'], params['password'])

    # Verify scene list is visible
    browser.wait_for_element(By.ID, "scene-list", timeout=10)
    scene_list = browser.find_element(By.ID, "scene-list")
    assert scene_list is not None, "Scene list not found"

  finally:
    browser.quit()
```

### 5. BAT Tests

**Purpose**: Quick sanity checks to verify basic system functionality

**Location**: `tests/functional/` or `tests/ui/` with `@pytest.mark.basic_acceptance` marker

**Characteristics**:

- Run via `make run_basic_acceptance_tests` or `pytest -m basic_acceptance`
- Test critical paths only
- Verify system is operational
- Run before more extensive tests

**When to create BAT tests**:

- After deployments
- Before running full test suite
- For quick validation of builds
- Testing core services are reachable

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

@pytest.mark.basic_acceptance
def test_rest_api_accessible(scenescape_env, params):
  """BAT test: Verify REST API is responding."""
  from scene_common.rest_client import RESTClient
  client = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert client.authenticate(params['user'], params['password'])
```

## Pytest Markers

Use pytest markers to categorize tests:

```python
import pytest

# Basic acceptance / BAT test (included in make run_basic_acceptance_tests)
@pytest.mark.basic_acceptance
def test_api_health():
    pass

# Preserve database state for next test (skip automatic DB restore)
@pytest.mark.preserve_db
def test_persistence_check():
    pass

# Kubernetes-only test (skipped on --backend=docker)
@pytest.mark.kubernetes_only
def test_k8s_deployment():
    pass

# Parametrized test
@pytest.mark.parametrize("input,expected", [
    (0, 0),
    (1, 1),
    (-1, 1),
])
def test_absolute_value(input, expected):
    assert abs(input) == expected
```

## Test Naming Conventions

**Test files**: `test_<module>.py`

**Test classes**: `Test<Feature>` or `<Feature>Test`

**Test functions**: `test_<what_is_being_tested>`

**Examples**:

- `test_point.py` → Tests for Point class
- `TestPointGeometry` → Test suite for Point geometry operations
- `test_point_creation_with_valid_coordinates` → Specific test case
- `test_point_creation_with_invalid_coordinates` → Negative test case
- `test_midpoint_calculation_between_two_points` → Descriptive test name

## Zephyr Test IDs

**All tests MUST include a Zephyr test ID** for CI tracking:

```python
TEST_NAME = "NEX-T10454"  # At top of file

# For functional/UI tests: set via record_xml_attribute
def test_something(scenescape_env, params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  # ... test logic ...

# For unit tests: set via conftest.py session hooks
# See "Unit Test conftest.py with Zephyr Tracking" below
```

## Conftest Patterns

### Root conftest.py (`tests/conftest.py`)

The root conftest manages the entire test session lifecycle:

- **Session-scoped fixtures**: `repo_root`, `version`, `secrets_dir`, `supass`, `loopback_hosts`, `install_shared_models`, `_compose_manager`
- **Function-scoped fixtures**: `scenescape_env` (orchestrates Docker Compose), `params` (connection parameters)
- **Pytest hooks**: `pytest_collection_modifyitems` (sorts tests by profile to minimize stack restarts), `pytest_addoption` (CLI options), `pytest_runtest_setup/call/makereport` (per-test logging and container log collection)

### Functional conftest.py (`tests/functional/conftest.py`)

Adds functional-specific fixtures:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from scene_common.rest_client import RESTClient

@pytest.fixture(scope="function")
def rest(params):
  """Authenticated REST client from params fixture."""
  client = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert client.authenticate(params['user'], params['password'])
  return client

@pytest.fixture(scope="function")
def scene_uid(rest, params):
  """UID of the demo scene."""
  name = params['scene_name']
  res = rest.getScenes({'name': name})
  scenes = res.get('results', []) if isinstance(res, dict) else []
  assert scenes, f"Scene '{name}' not found"
  return scenes[0]['uid']
```

Also provides `pytest_generate_tests` for `--env-profiles` matrix parametrization and `_env_matrix_setup` fixture.

### Unit Test conftest.py with Zephyr Tracking

**All unit test conftest.py files MUST include TEST_NAME and session hooks** for CI/Zephyr tracking:

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration for [module] unit tests."""

import pytest
from unittest.mock import Mock, MagicMock
import tests.common_test_utils as common

TEST_NAME = "NEX-T#####"  # Always assign a Zephyr test ID

@pytest.fixture
def mock_database():
    """Mock database for unit tests"""
    mock = MagicMock()
    return mock

def pytest_sessionstart():
    """! Executes at the beginning of the test session. """
    print(f"Executing: {TEST_NAME}")
    return

def pytest_sessionfinish(exitstatus):
    """! Executes at the end of the test session. """
    common.record_test_result(TEST_NAME, exitstatus)
    return
```

**Requirements**:

- `TEST_NAME` must be assigned a valid Zephyr test ID (format: `NEX-T#####`)
- `pytest_sessionstart()` logs the test execution
- `pytest_sessionfinish(exitstatus)` records the test result via `common.record_test_result()`
- Import `tests.common_test_utils` to access the result recording function

## Test Data Management

**Use fixtures for test data:**

```python
@pytest.fixture
def valid_detection():
    """Provide valid detection data"""
    return {
        "id": "camera1",
        "timestamp": "2025-01-06T12:00:00.000Z",
        "objects": {
            "person": [{
                "id": 1,
                "category": "person",
                "bounding_box": {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2}
            }]
        }
    }

@pytest.fixture
def invalid_detections():
    """Provide various invalid detection formats"""
    return [
        {},  # Empty
        {"id": "camera1"},  # Missing timestamp and objects
        {"id": "camera1", "timestamp": "invalid"},  # Invalid timestamp
        {"id": "camera1", "timestamp": "2025-01-06T12:00:00.000Z", "objects": None},  # Null objects
    ]
```

## Assertion Best Practices

**Be specific with assertions:**

```python
# Good - specific assertions
assert response.status_code == 200
assert 'id' in data
assert data['name'] == expected_name
assert len(results) > 0

# Better - with messages
assert response.status_code == 200, f"Expected 200, got {response.status_code}"
assert 'id' in data, "Response missing required 'id' field"

# Good - testing exceptions
with pytest.raises(ValueError, match="Invalid coordinates"):
    geometry.Point(None, None)

# Good - approximate comparisons
assert math.isclose(result, 3.14159, rel_tol=1e-5)
```

## Common Testing Patterns

### Testing Async Code

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test asynchronous function"""
    result = await async_operation()
    assert result == expected
```

### Testing with Temporary Files

```python
import tempfile
from pathlib import Path

def test_file_processing():
    """Test file processing with temporary file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("test data")

        result = process_file(test_file)
        assert result is not None
        # File automatically cleaned up
```

### Testing Time-Dependent Code

```python
from unittest.mock import patch
import datetime

@patch('module.datetime')
def test_time_dependent_function(mock_datetime):
    """Test function that depends on current time"""
    # Fix time to a known value
    mock_datetime.now.return_value = datetime.datetime(2025, 1, 6, 12, 0, 0)

    result = function_that_uses_time()
    assert result == expected_value_at_fixed_time
```

## Running Tests

```bash
# Setup (from repo root)
make setup-tests                                      # Build test images, secrets, venv
                                                      # Create venv + install deps + build C++ extensions

# Make targets (from repo root)
make run_basic_acceptance_tests                       # BAT tests (basic_acceptance marker)
make run_standard_tests                               # Functional + UI + security + stability
make run_functional_tests                             # Functional
make run_ui_tests                                     # UI/Selenium tests only
make run_unit_tests                                   # Unit tests only (sscape_tests)
make run_metric_tests                                 # Tracker quality metrics
make run_performance_tests                            # Inference performance + geometry
make run_stability_tests HOURS=24                     # Long-running stability

# Direct pytest (from repo root, with tests/.venv activated)
pytest tests/sscape_tests                             # All unit tests
pytest tests/functional                               # All functional tests
pytest tests/ui                                       # All UI tests
pytest tests/functional/test_roi_mqtt.py              # Single functional test
pytest tests/ -m basic_acceptance                     # BAT suite only

# Specific test
pytest tests/sscape_tests/geometry/test_point.py::TestPoint::test_constructor

# Save results
pytest tests/ --junitxml=results.xml 2>&1 | tee output.log

# Multi-backend testing
pytest tests/functional --backend=docker              # Docker only (default)
pytest tests/functional --backend=kubernetes          # Kubernetes only
pytest tests/functional --backend=all                 # Both backends

# Multi-profile testing
pytest tests/functional/test_roi_mqtt.py --env-profiles=full_stack,full_stack_with_mapping

# Container log collection
pytest tests/functional --collect-container-logs=failed   # Collect on failure (default)
pytest tests/functional --collect-container-logs=all      # Collect always
pytest tests/functional --collect-container-logs=none     # Never collect
```

## Test Checklist

This checklist is mandatory before marking any testing task complete.
If any item is not satisfied, the final response must explicitly state why.
When creating or modifying tests, verify:

- [ ] Test has Zephyr ID (NEX-T#####)
- [ ] Test file named `test_*.py`
- [ ] Test functions named `test_*`
- [ ] Both positive and negative cases covered
- [ ] Boundary conditions tested
- [ ] At least one negative case exists per function or behavior under test, unless explicitly not applicable
- [ ] Appropriate markers applied (`@pytest.mark.basic_acceptance`, `@pytest.mark.preserve_db`, etc.)
- [ ] Functional/UI tests declare `SCENESCAPE_SPEC` with correct `ServiceProfile`
- [ ] Mocking used for external dependencies (unit tests)
- [ ] Real data used for integration tests
- [ ] Proper setup and teardown
- [ ] Clear, descriptive test names
- [ ] Assertions have helpful messages
- [ ] Test is independent (doesn't rely on other tests)
- [ ] Fixtures used for shared data
- [ ] Documentation strings explain what is being tested
- [ ] Repo-preferred test command used for validation (prefer `pytest tests/<path>/<test_file>.py` for targeted runs; use `make run_*` only for broad suite sweeps)
- [ ] New or changed tests executed after the last code edit
- [ ] Final response includes current pass/fail status and any warnings or known gaps

## Quick Reference

**Unit Test**: Fast, isolated, mocked dependencies, in `tests/sscape_tests/`
**Functional Test**: Real services via `SCENESCAPE_SPEC` + `FuncTestSpec`, in `tests/functional/`
**Integration Test**: Cross-service interactions, real data, in `tests/functional/` or `tests/system/`
**UI Test**: Selenium browser automation via `AUTH_BROWSER`, in `tests/ui/`
**Smoke Test**: Quick sanity checks, `@pytest.mark.basic_acceptance` marker

**Always create BOTH positive (happy path) and negative (error cases) tests!**
