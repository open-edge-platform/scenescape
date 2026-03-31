# API Test Framework

A data-driven, multi-step REST API test framework built on pytest. Tests are defined as JSON scenario files.

---

## Project Structure

```
tests
├── api
    ├── test_sscape_api.py        # Main test runner
    ├── mapping_client.py         # Mapping/reconstruction REST client
    ├── conftest.py               # Pytest configuration
    ├── scenarios/                # Default directory for test scenario files
    │   ├── camera_api.json
    │   ├── scene_api.json
    │   ├── sensor_api.json
    │   └── ...
    └── api_test.log              # Auto-generated log file
```

---

## Requirements

- Python 3.8+
- pytest
- requests
- `scene_common` package (built from source)

Install dependencies:
```bash
pip install pytest requests
```

### Setup `scene_common`

The test framework depends on the `scene_common` package.

```bash
make -C scene_common
# Or add source directory to PYTHONPATH 
export PYTHONPATH=$(pwd)/scene_common/src:$PYTHONPATH
```

---

## Environment Variables

| Variable            | Default                        | Description                                  |
|---------------------|--------------------------------|----------------------------------------------|
| `API_TOKEN`         | `token`                        | Authentication token for API calls           |
| `API_BASE_URL`      | `https://localhost`            | Base URL (scheme + host only); the test runner appends the API path internally                   |


### Mapping Service Setup

The mapping/reconstruction tests require the `scenescape-mapping` service to be running.
Upload `ParkingVideoTrimmed2.mp4` into `tests/api/test_media/` to verify excessively large input.

---

## Running Tests

### Basic syntax
```bash
pytest -s test_sscape_api.py --file <path> [--test_case <ID>] [--junitxml=test-results.xml]
```

### Run all scenarios from the default `scenarios/` folder
```bash
pytest -s test_sscape_api.py
```

### Run all scenarios from a specific JSON file
```bash
pytest -s test_sscape_api.py --file scenarios/scene_api.json
```

### Run all scenarios from a folder
```bash
pytest -s test_sscape_api.py --file scenarios/
```

### Run a single test case by ID
```bash
pytest -s test_sscape_api.py --file scenarios/scene_api.json --test_case Vision_AI/SSCAPE/API/SCENE/01
```

### Run with JUnit XML report (for CI/CD)
```bash
pytest -s test_sscape_api.py --file scenarios/scene_api.json --junitxml=test-results.xml
```

### Combined example
```bash
pytest -s test_sscape_api.py \
  --file scenarios/scene_api.json \
  --test_case Vision_AI/SSCAPE/API/SCENE/01 \
  --junitxml=test-results.xml
```

---

## Scenario File Format

Scenarios are JSON files containing an array of test cases. Each test case has one or more sequential steps.

### Top-level structure
```json
[
  { "test_name": "test_case_1" },
  { "test_name": "test_case_2" }
]
```

### Test case fields

| Field        | Required | Description                                  |
|--------------|----------|----------------------------------------------|
| `test_name`  | Yes      | Unique identifier used with `--test_case`    |
| `test_steps` | Yes      | Array of steps executed in order             |

### Step fields

| Field               | Required | Description                                                                            |
|---------------------|----------|----------------------------------------------------------------------------------------|
| `step_name`         | No       | Human-readable label shown in logs and failure messages                                |
| `api`               | Yes      | API group: `camera`, `scene`, `sensor`, `region`, `tripwire`, `user`, `asset`, `child` |
| `method`            | Yes      | RESTClient method name (e.g. `createCamera`, `getScene`)                               |
| `request`           | No       | Arguments passed to the method (see key mapping below)                                 |
| `expected_status`   | No       | Assertions on the response (currently `status_code`)                                   |
| `save`              | No       | Variables to extract from the response for later steps                                 |
| `validate`          | No       | Response body field assertions using dot-notation (partial match)                      |
| `expected_body`     | No       | Full response body structure validation (exact match)                                      |

### Request key mapping

The JSON request keys are automatically mapped to RESTClient parameter names:

| JSON key | RESTClient parameter | Usage                        |
|----------|----------------------|------------------------------|
| `body`   | `data`               | Request body (POST/PUT)      |
| `uid`    | `uid`                | Path parameter               |

List methods (e.g. `getCameras`, `getScenes`) automatically receive `filter=None` if no filter is provided in the request.

---

## Full Scenario Example

```json
[
  {
    "test_name": "Vision_AI/SSCAPE/API/SCENE/01: Create scene with only required properties",
    "test_steps": [
      {
        "step_name": "Create Scene",
        "api": "scene",
        "method": "createScene",
        "request": {
          "body": {
            "name": "Scene1",
            "use_tracker": true,
            "output_lla": false
          }
        },
        "expected_status": {
          "status_code": 201
        },
        "save": {
          "SCENE_UID": "uid"
        }
      }
    ]
  },
  {
    "test_name": "Vision_AI/SSCAPE/API/SCENE/08: Update scene with minimal valid payload",
    "test_steps": [
      {
        "step_name": "Update Scene",
        "api": "scene",
        "method": "updateScene",
        "request": {
          "uid": "${SCENE_UID}",
          "body": {
            "name": "Scene1_Updated",
            "use_tracker": false,
            "output_lla": true
          }
        },
        "expected_status": {
          "status_code": 200
        }
      },
      {
        "step_name": "Verify resource was updated",
        "api": "scene",
        "method": "getScene",
        "request": {
          "uid": "${SCENE_UID}"
        },
        "expected_status": {
          "status_code": 200
        },
        "expected_body": {
          "uid": "${SCENE_UID}",
          "name": "Scene1_Updated",
          "map_type": "map_upload",
          "use_tracker": false,
          "output_lla": true,
          "mesh_translation": [
            0,
            0,
            0
          ],
          "mesh_rotation": [
            0,
            0,
            0
          ],
          "mesh_scale": [
            1.0,
            1.0,
            1.0
          ],
          "regulated_rate": 30.0,
          "external_update_rate": 30.0,
          "camera_calibration": "Manual",
          "apriltag_size": 0.162,
          "number_of_localizations": 50,
          "global_feature": "netvlad",
          "local_feature": {
            "sift": {}
          },
          "matcher": {
            "NN-ratio": {}
          },
          "minimum_number_of_matches": 20,
          "inlier_threshold": 0.5,
          "geospatial_provider": "google",
          "map_zoom": 15.0,
          "map_bearing": 0.0
        }
      }
    ]
  }
]
```

---

## Variable Substitution

Values saved from one step can be referenced in later steps using `${VAR_NAME}` syntax.

### Saving a value
```json
"save": {
  "SCENE_UID": "uid"
}
```
This extracts the `uid` field from the response body and stores it as `SCENE_UID`. The value is also set as an environment variable for the duration of the test run.

### Using a saved value
```json
"request": {
  "uid": "${SCENE_UID}"
}
```

Variable substitution works recursively in any nested `request` object.

---

## Response Validation

### Status code assertion
Always checked if `expected.status_code` is set:
```json
"expected_status": {
  "status_code": 201
}
```

### Body field assertions
Check specific fields in the response body using dot-notation for nested fields:
```json
"validate": {
  "name": "Scene1",
  "mesh_scale": [1.0, 1.0, 1.0]
}
```

If any assertion fails, the step fails with a detailed diff message showing expected vs actual values.

---

## Logging

All runs produce two log outputs:

| Output         | Level   | Location                          |
|----------------|---------|-----------------------------------|
| Console        | INFO    | stdout (visible with `-s` flag)   |
| File           | DEBUG   | `api_test.log` next to test file  |

The log file is overwritten on each run. Debug output includes full request data, response status, response body, and saved variable values.

---

## Available API Methods

All methods live in `RESTClient` unless noted otherwise:

| API group  | Methods                                                      | Client          |
|------------|--------------------------------------------------------------|-----------------|
| `scene`    | `getScenes`, `createScene`, `getScene`, `updateScene`, `deleteScene` | `RESTClient` |
| `camera`   | `getCameras`, `createCamera`, `getCamera`, `updateCamera`, `deleteCamera` | `RESTClient` |
| `sensor`   | `getSensors`, `createSensor`, `getSensor`, `updateSensor`, `deleteSensor` | `RESTClient` |
| `region`   | `getRegions`, `createRegion`, `getRegion`, `updateRegion`, `deleteRegion` | `RESTClient` |
| `tripwire` | `getTripwires`, `createTripwire`, `getTripwire`, `updateTripwire`, `deleteTripwire` | `RESTClient` |
| `user`     | `getUsers`, `createUser`, `getUser`, `updateUser`, `deleteUser` | `RESTClient` |
| `asset`    | `getAssets`, `createAsset`, `getAsset`, `updateAsset`, `deleteAsset` | `RESTClient` |
| `child`    | `getChildScene`, `updateChildScene`                          | `RESTClient`    |
| `mapping`  | `performReconstruction`, `getReconstructionStatus`, `healthCheckEndpoint`, `listModels` | `MappingClient` |

---

## Adding New Tests

1. Create or open a JSON file in `scenarios/`
2. Add a new object to the array following the schema above
3. Use `test_name` in the format `Vision_AI/SSCAPE/Endpoint/TestCase_No: Test case title` for consistency
4. Run with `--test_case` to verify before committing

No Python changes required.
