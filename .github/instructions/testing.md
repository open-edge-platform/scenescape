# AI Agent Guide: Creating Test Cases for SceneScape

This guide provides comprehensive instructions for AI agents to create high-quality, well-categorized test cases for the SceneScape project.

## Test Philosophy

**Always create BOTH positive and negative test cases:**

- **Positive tests**: Verify expected behavior with valid inputs
- **Negative tests**: Verify proper error handling with invalid inputs, edge cases, and boundary conditions

**Test isolation and independence:**

- Tests should not depend on execution order
- Each test should set up its own data and clean up after itself
- Use mocking to isolate units from external dependencies

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

- Require running Docker containers
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

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
import json
import time

TEST_NAME = "NEX-T##### "  # Always include Zephyr test ID

class CameraManagementTest(FunctionalTest):
    """Test camera management via REST API"""

    def setUp(self):
        """Setup test with real REST client"""
        super().setUp()
        self.scene_id = self.args.scene_id
        self.camera_data = {
            "name": "test_camera_1",
            "type": "rgb",
            "location": {"x": 0, "y": 0, "z": 3}
        }

    def tearDown(self):
        """Cleanup test data"""
        # Delete created cameras
        if hasattr(self, 'created_camera_id'):
            self.rest.delete(f"/scenes/{self.scene_id}/cameras/{self.created_camera_id}")
        super().tearDown()

    # Positive tests
    def test_create_camera(self):
        """Test creating a camera via REST API"""
        response = self.rest.post(
            f"/scenes/{self.scene_id}/cameras",
            json=self.camera_data
        )

        assert response.status_code == 201
        data = response.json()
        assert 'id' in data
        assert data['name'] == self.camera_data['name']

        self.created_camera_id = data['id']

    def test_get_camera(self):
        """Test retrieving camera details"""
        # First create a camera
        create_response = self.rest.post(
            f"/scenes/{self.scene_id}/cameras",
            json=self.camera_data
        )
        camera_id = create_response.json()['id']
        self.created_camera_id = camera_id

        # Now retrieve it
        get_response = self.rest.get(
            f"/scenes/{self.scene_id}/cameras/{camera_id}"
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data['id'] == camera_id
        assert data['name'] == self.camera_data['name']

    # Negative tests
    def test_create_camera_invalid_scene(self):
        """Test creating camera with non-existent scene ID"""
        response = self.rest.post(
            "/scenes/invalid-scene-id/cameras",
            json=self.camera_data
        )

        assert response.status_code == 404

    def test_create_camera_missing_required_field(self):
        """Test creating camera without required fields"""
        invalid_data = {"name": "incomplete_camera"}  # Missing type and location

        response = self.rest.post(
            f"/scenes/{self.scene_id}/cameras",
            json=invalid_data
        )

        assert response.status_code == 400

    def test_get_nonexistent_camera(self):
        """Test retrieving camera that doesn't exist"""
        response = self.rest.get(
            f"/scenes/{self.scene_id}/cameras/nonexistent-id"
        )

        assert response.status_code == 404

    def test_delete_camera_twice(self):
        """Test that deleting same camera twice fails"""
        # Create and delete camera
        create_response = self.rest.post(
            f"/scenes/{self.scene_id}/cameras",
            json=self.camera_data
        )
        camera_id = create_response.json()['id']

        delete_response = self.rest.delete(
            f"/scenes/{self.scene_id}/cameras/{camera_id}"
        )
        assert delete_response.status_code == 204

        # Try to delete again
        second_delete = self.rest.delete(
            f"/scenes/{self.scene_id}/cameras/{camera_id}"
        )
        assert second_delete.status_code == 404


# Pytest entry point
def test_camera_management(request, record_xml_attribute):
    """Pytest entry point for camera management tests"""
    test = CameraManagementTest(TEST_NAME, request, record_xml_attribute)
    test.run()
```

**MQTT functional test example**:

```python
class MQTTDetectionTest(FunctionalTest):
    """Test detection message flow through MQTT"""

    def setUp(self):
        """Setup MQTT connection"""
        super().setUp()
        self.detection_received = False
        self.tracking_data = None

        # Setup MQTT subscriber
        self.pubsub.addCallback("tracking/+", self.on_tracking)

    def on_tracking(self, client, userdata, message):
        """Callback for tracking messages"""
        self.tracking_data = json.loads(message.payload.decode('utf-8'))
        self.detection_received = True

    # Positive test
    def test_detection_produces_tracking(self):
        """Test that detection message produces tracking output"""
        detection = {
            "id": "camera1",
            "timestamp": get_iso_time(),
            "objects": {
                "person": [{
                    "id": 1,
                    "category": "person",
                    "bounding_box": {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2}
                }]
            }
        }

        # Publish detection
        self.pubsub.publish("detection/camera1", json.dumps(detection))

        # Wait for tracking response
        timeout = 10
        elapsed = 0
        while not self.detection_received and elapsed < timeout:
            time.sleep(0.5)
            elapsed += 0.5

        assert self.detection_received, "No tracking message received"
        assert self.tracking_data is not None
        assert 'objects' in self.tracking_data

    # Negative test
    def test_invalid_detection_rejected(self):
        """Test that malformed detection is rejected"""
        invalid_detection = {
            "id": "camera1",
            # Missing timestamp and objects
        }

        # Publish invalid detection
        self.pubsub.publish("detection/camera1", json.dumps(invalid_detection))

        # Wait briefly
        time.sleep(2)

        # Should not receive tracking
        assert not self.detection_received, "Invalid detection should not produce tracking"
```

### 3. Integration Tests

**Purpose**: Test cross-container interactions and service integration with real data

**Location**: `tests/functional/` or `tests/system/`

**Characteristics**:

- Require multiple running containers
- Test real service-to-service communication
- Use actual databases, message brokers, and services
- Test realistic data flows
- Longer execution times

**When to create integration tests**:

- Testing Scene Controller → Manager → Database flow
- Testing MQTT → Controller → REST API chain
- Testing calibration service with real image data
- Testing mapping service with controller integration
- Testing complete detection → tracking → storage pipeline

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
import json
import time
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T#####"

class EndToEndTrackingTest(FunctionalTest):
    """Integration test for complete tracking pipeline"""

    def setUp(self):
        """Setup REST and MQTT connections"""
        super().setUp()
        self.tracking_results = []
        self.pubsub.addCallback("tracking/+", self.on_tracking)

    def on_tracking(self, client, userdata, message):
        """Collect tracking messages"""
        data = json.loads(message.payload.decode('utf-8'))
        self.tracking_results.append(data)

    # Positive integration test
    def test_complete_detection_tracking_storage_pipeline(self):
        """Test full pipeline: detection → controller → tracking → database"""

        # Step 1: Create scene via REST API
        scene_data = {
            "name": "Integration Test Scene",
            "floor_plan": {"width": 10, "height": 10}
        }
        scene_response = self.rest.post("/scenes", json=scene_data)
        assert scene_response.status_code == 201
        scene_id = scene_response.json()['id']

        # Step 2: Add camera to scene
        camera_data = {
            "name": "test_camera",
            "type": "rgb",
            "location": {"x": 5, "y": 5, "z": 3}
        }
        camera_response = self.rest.post(
            f"/scenes/{scene_id}/cameras",
            json=camera_data
        )
        assert camera_response.status_code == 201
        camera_id = camera_response.json()['id']

        # Step 3: Publish detection via MQTT
        detection = {
            "id": camera_id,
            "timestamp": get_iso_time(),
            "objects": {
                "person": [{
                    "id": 1,
                    "category": "person",
                    "bounding_box": {"x": 0.5, "y": 0.5, "width": 0.1, "height": 0.2}
                }]
            }
        }
        self.pubsub.publish(f"detection/{camera_id}", json.dumps(detection))

        # Step 4: Wait for tracking output
        timeout = 15
        elapsed = 0
        while len(self.tracking_results) == 0 and elapsed < timeout:
            time.sleep(0.5)
            elapsed += 0.5

        assert len(self.tracking_results) > 0, "No tracking output received"
        tracking = self.tracking_results[0]
        assert 'objects' in tracking

        # Step 5: Verify data was stored in database via REST API
        objects_response = self.rest.get(f"/scenes/{scene_id}/objects")
        assert objects_response.status_code == 200
        objects = objects_response.json()
        assert len(objects) > 0

        # Cleanup
        self.rest.delete(f"/scenes/{scene_id}")

    # Negative integration test
    def test_detection_with_uncalibrated_camera_rejected(self):
        """Test that detection from uncalibrated camera is rejected"""

        # Create scene and camera without calibration
        scene_response = self.rest.post("/scenes", json={"name": "Test Scene"})
        scene_id = scene_response.json()['id']

        camera_response = self.rest.post(
            f"/scenes/{scene_id}/cameras",
            json={"name": "uncalibrated_cam", "type": "rgb"}
        )
        camera_id = camera_response.json()['id']

        # Publish detection
        detection = {
            "id": camera_id,
            "timestamp": get_iso_time(),
            "objects": {"person": [{"id": 1, "category": "person", "bounding_box": {}}]}
        }
        self.pubsub.publish(f"detection/{camera_id}", json.dumps(detection))

        # Wait briefly
        time.sleep(3)

        # Should not produce tracking
        assert len(self.tracking_results) == 0, "Uncalibrated camera should not produce tracking"

        # Cleanup
        self.rest.delete(f"/scenes/{scene_id}")
```

### 4. UI Tests

**Purpose**: Test web interface functionality using browser automation

**Location**: `tests/ui/`

**Characteristics**:

- Use Selenium WebDriver
- Require running web server and backend services
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
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

class TestSceneManagementUI:
    """UI tests for scene management interface"""

    @pytest.fixture(scope="class")
    def driver(self, params):
        """Setup Selenium WebDriver"""
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)

        # Login
        driver.get(params['weburl'])
        driver.find_element(By.ID, "username").send_keys(params['user'])
        driver.find_element(By.ID, "password").send_keys(params['password'])
        driver.find_element(By.ID, "login-button").click()

        yield driver
        driver.quit()

    # Positive UI test
    def test_create_scene_via_ui(self, driver, params):
        """Test creating a scene through the web interface"""
        # Navigate to scenes page
        driver.get(f"{params['weburl']}/scenes")

        # Click create scene button
        create_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "create-scene-btn"))
        )
        create_button.click()

        # Fill in scene form
        name_input = driver.find_element(By.ID, "scene-name")
        name_input.send_keys("UI Test Scene")

        # Submit form
        submit_button = driver.find_element(By.ID, "submit-scene")
        submit_button.click()

        # Verify success message
        success_msg = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "success-message"))
        )
        assert "Scene created successfully" in success_msg.text

        # Verify scene appears in list
        scene_list = driver.find_element(By.ID, "scene-list")
        assert "UI Test Scene" in scene_list.text

    # Negative UI test
    def test_create_scene_with_empty_name(self, driver, params):
        """Test that creating scene with empty name shows error"""
        driver.get(f"{params['weburl']}/scenes")

        # Click create button
        create_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "create-scene-btn"))
        )
        create_button.click()

        # Leave name field empty and submit
        submit_button = driver.find_element(By.ID, "submit-scene")
        submit_button.click()

        # Verify error message
        error_msg = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "error-message"))
        )
        assert "Scene name is required" in error_msg.text

    def test_scene_list_pagination(self, driver, params):
        """Test scene list pagination"""
        driver.get(f"{params['weburl']}/scenes")

        # Check if pagination controls exist when there are many scenes
        try:
            pagination = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "pagination"))
            )

            # Click next page
            next_button = pagination.find_element(By.CLASS_NAME, "next-page")
            next_button.click()

            # Verify page changed
            WebDriverWait(driver, 5).until(
                EC.staleness_of(next_button)
            )

        except TimeoutException:
            # No pagination (not enough scenes)
            pytest.skip("Not enough scenes for pagination test")
```

### 5. Smoke Tests

**Purpose**: Quick sanity checks to verify basic system functionality

**Location**: `tests/functional/` with `@pytest.mark.smoke` marker

**Characteristics**:

- Fast execution (< 30 seconds total)
- Test critical paths only
- Verify system is operational
- Run before more extensive tests

**When to create smoke tests**:

- After deployments
- Before running full test suite
- For quick validation of builds
- Testing core services are reachable

**Structure**:

```python
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from tests.functional import FunctionalTest

@pytest.mark.smoke
class SmokeTest(FunctionalTest):
    """Basic smoke tests for system health"""

    def test_rest_api_accessible(self):
        """Smoke test: Verify REST API is responding"""
        response = self.rest.get("/health")
        assert response.status_code == 200

    def test_mqtt_broker_accessible(self):
        """Smoke test: Verify MQTT broker is accessible"""
        assert self.pubsub.isConnected(), "MQTT broker not accessible"

    def test_database_accessible(self):
        """Smoke test: Verify database is accessible via REST API"""
        response = self.rest.get("/scenes")
        assert response.status_code in [200, 401]  # 200 OK or 401 if not authenticated

    def test_scene_controller_responding(self):
        """Smoke test: Verify scene controller is processing messages"""
        # Publish a simple message
        test_msg = {"test": "ping"}
        self.pubsub.publish("test/smoke", json.dumps(test_msg))

        # Just verify no crashes (negative test would be timeout/error)
        time.sleep(1)
        assert True  # If we got here, controller didn't crash
```

## Pytest Markers

Use pytest markers to categorize tests:

```python
import pytest

# Unit test
@pytest.mark.unit
def test_geometry_calculation():
    pass

# Integration test
@pytest.mark.integration
def test_mqtt_to_database_flow():
    pass

# Slow test
@pytest.mark.slow
def test_long_running_calibration():
    pass

# Smoke test
@pytest.mark.smoke
def test_api_health():
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

def pytest_sessionstart():
    """Executes at the beginning of the session."""
    print(f"Executing: {TEST_NAME}")
    return

def pytest_sessionfinish(exitstatus):
    """Executes at the end of the session."""
    common.record_test_result(TEST_NAME, exitstatus)
    return
```

## Conftest Patterns

**conftest.py** provides shared fixtures for test modules:

```python
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import Mock

# Session-level fixtures (created once per test session)
@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration"""
    return {
        "timeout": 30,
        "retry_count": 3,
    }

# Module-level fixtures (created once per test module)
@pytest.fixture(scope="module")
def database_connection():
    """Provide database connection for all tests in module"""
    conn = create_connection()
    yield conn
    conn.close()

# Function-level fixtures (created for each test function)
@pytest.fixture
def sample_data():
    """Provide fresh sample data for each test"""
    return {"id": "test", "value": 123}

# Parametrized fixtures
@pytest.fixture(params=[2, 3, 4])
def dimensions(request):
    """Test with different dimensions"""
    return request.param

# Command-line options
def pytest_addoption(parser):
    parser.addoption("--user", required=True, help="User for authentication")
    parser.addoption("--password", required=True, help="Password for authentication")

@pytest.fixture
def credentials(request):
    """Provide credentials from command line"""
    return {
        'user': request.config.getoption('--user'),
        'password': request.config.getoption('--password'),
    }
```

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
# Run all unit tests
make -C tests unit-tests

# Run specific test module
pytest tests/sscape_tests/geometry/test_point.py -v

# Run specific test
pytest tests/sscape_tests/geometry/test_point.py::TestPoint::test_constructor -v

# Run tests with markers
pytest -m unit  # Only unit tests
pytest -m "not slow"  # Exclude slow tests
pytest -m smoke  # Only smoke tests

# Run with coverage
pytest --cov=src --cov-report=html

# Run functional tests (requires running containers)
make run_basic_acceptance_tests

# Run tests with verbose output
pytest -v -s  # -s shows print statements
```

## Test Checklist

When creating a new test, verify:

- [ ] Test has Zephyr ID (NEX-T#####)
- [ ] Test file named `test_*.py`
- [ ] Test functions named `test_*`
- [ ] Both positive and negative cases covered
- [ ] Boundary conditions tested
- [ ] Appropriate markers applied (`@pytest.mark.unit`, etc.)
- [ ] Mocking used for external dependencies (unit tests)
- [ ] Real data used for integration tests
- [ ] Proper setup and teardown
- [ ] Clear, descriptive test names
- [ ] Assertions have helpful messages
- [ ] Test is independent (doesn't rely on other tests)
- [ ] Fixtures used for shared data
- [ ] Documentation strings explain what is being tested

## Quick Reference

**Unit Test**: Fast, isolated, mocked dependencies
**Functional Test**: Real services, end-to-end workflows
**Integration Test**: Cross-service interactions, real data
**UI Test**: Browser automation, user interactions
**Smoke Test**: Quick sanity checks, critical paths only

**Always create BOTH positive (happy path) and negative (error cases) tests!**
