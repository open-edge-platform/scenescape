# HLOC Patch Verification Tests

Modular test suite for verifying HLOC patches maintain functional equivalence after upgrading to latest main.

## Quick Start

```bash
# 1. Build the test image
cd autocalibration
make test-build

# 2. Enter the test container
docker run --rm -it --entrypoint bash scenescape-autocalibration-test:latest

# 3. Navigate to tests directory
cd /opt/hloc-tests

# 4. Run all tests
./run_tests.sh

# OR use pytest directly
pytest -v
```

**Note**: Test dependencies are pre-installed in the `autocalibration-test` container.

## Test Structure

```
tests/
├── test_utils.py                # Shared test utilities
├── test_api.py                  # API surface checks (imports, signatures, classes)
├── test_extraction.py           # Feature extraction functionality
├── test_matching.py             # Feature matching functionality
├── test_matchers.py             # Custom matchers (LoFTR, QTA-LoFTR, dense matching)
├── test_database.py             # COLMAP database operations
├── test_workflows.py            # Reconstruction and pipeline workflows
├── test_localize_scenescape.py  # SceneScape localization pipeline (pose_from_cluster, quaternion utils)
└── run_tests.sh                 # Test runner script
```

## Running Tests

### Using the Test Runner Script

```bash
# All tests (default)
./run_tests.sh

# API tests only (quick validation)
./run_tests.sh . api

# Functional tests only
./run_tests.sh . functional

# Specific test by name
./run_tests.sh test_api test

# With coverage report
./run_tests.sh . coverage

# Using pytest directly
./run_tests.sh . pytest
```

### Using pytest Directly

```bash
# All tests
pytest -v

# Single test file
pytest test_api.py -v

# Single test function
pytest test_api.py::TestImports::test_pycolmap_imports -v

# With coverage
pytest --cov=../hloc --cov-report=html --cov-report=term
```

### Inside Docker Container

```bash
# Enter the test container
docker run --rm -it --entrypoint bash scenescape-autocalibration-test:latest

# Navigate to tests directory
cd /opt/hloc-tests

# Run tests using the script
./run_tests.sh              # All tests
./run_tests.sh . api        # API tests only
./run_tests.sh . functional # Functional tests
./run_tests.sh . coverage   # With coverage report

# Or directly
python3 run_tests.py --test api
```

### pose_from_cluster Tests Only

```bash
cd autocalibration
make verify-pose-from-cluster

# Or directly
cd autocalibration/src/reloc/tests
pytest test_localize_scenescape.py::TestPoseFromCluster -v
```

### Individual Test File

```bash
cd autocalibration/src/reloc/tests
python3 test_api.py
python3 test_extraction.py
# ... etc
```

## Test Categories

### API Surface Tests (`test_api.py`)

- ✅ Core module imports
- ✅ Custom module imports (SceneScape additions)
- ✅ Function signature verification
- ✅ Class existence checks

**Dependencies**: None (only imports)  
**Run Time**: < 1 second

### Feature Extraction (`test_extraction.py`)

- ✅ **DoG extractor API compatibility** (pycolmap >=0.6.0)
- ✅ Creates synthetic test images
- ✅ Extracts keypoints and descriptors
- ✅ Validates H5 output format
- ✅ Verifies descriptor dimensions

**Dependencies**: PIL, numpy, h5py, torch  
**Run Time**: 5-10 seconds

**Critical Test**: DoG extractor API verification catches pycolmap version mismatches at build time, preventing runtime errors like `ValueError: not enough values to unpack`.

### Feature Matching (`test_matching.py`)

- ✅ Tests SuperGlue matching
- ✅ Validates match scores
- ✅ Checks output format

**Dependencies**: PIL, numpy, h5py, torch  
**Run Time**: 10-15 seconds

### Custom Matchers (`test_matchers.py`)

- ✅ Tests match_dense module
- ✅ LoFTR instantiation and methods
- ✅ QTA-LoFTR instantiation and methods

**Dependencies**: torch  
**Run Time**: < 1 second (skips weight loading)

### Database Operations (`test_database.py`)

- ✅ COLMAP database creation
- ✅ Camera/image/keypoint insertion
- ✅ Query operations

**Dependencies**: numpy, sqlite3  
**Run Time**: < 1 second

### Workflows (`test_workflows.py`)

- ✅ Reconstruction API verification
- ✅ Triangulation API verification
- ✅ SceneScape pipeline checks

**Dependencies**: None (API checks only)  
**Run Time**: < 1 second

### SceneScape Localization (`test_localize_scenescape.py`)

- ✅ Quaternion conversion utilities (qxyzw_to_qwxyz, qwxyz_to_qxyzw)
- ✅ Quaternion inverse with translation (qxyzwtinv)
- ✅ `pose_from_cluster` function signature and defaults
- ✅ `pose_from_cluster` with empty arrays (edge case)
- ✅ `pose_from_cluster` with too few matches (<= 4)
- ✅ `pose_from_cluster` with valid depth data
- ✅ `pose_from_cluster` with dense matching mode
- ✅ Main function signature verification
- ✅ Depth scale and filtering validation
- ✅ Coordinate system consistency checks

**Dependencies**: numpy, h5py, PIL, scipy, pycolmap, open3d  
**Run Time**: ~2-5 seconds (includes mock file I/O)

**Important**: These tests verify the core localization logic that was affected by pycolmap 0.6.0 API changes, including:

- Empty array handling (prevents NoneType errors)
- Camera object creation
- Points format conversion (column vectors)
- Estimation options configuration

## Expected Output

### Successful Run

```
================================================================================
HLOC Patch Verification
================================================================================

Running 7 test suite(s)...

Running test_api.py...
[API test output...]

Running test_extraction.py...
[Extraction test output...]

[... more tests ...]

================================================================================
SUMMARY
================================================================================
  ✅ PASSED: test_api.py
  ✅ PASSED: test_extraction.py
  ✅ PASSED: test_matching.py
  ✅ PASSED: test_matchers.py
  ✅ PASSED: test_database.py
  ✅ PASSED: test_workflows.py

================================================================================
Total: 7/7 test suites passed
================================================================================

✅ All verification tests passed!
The patched HLOC is functionally equivalent and ready for production.
```

## Integration with Docker Build

The Dockerfile runs a lightweight build-time test automatically:

```dockerfile
python3 /tmp/reloc-build-test.py
```

This ensures patches apply correctly. The full test suite can be run after build:

```bash
docker run --rm -it --entrypoint bash scenescape-autocalibration-test:latest
cd /opt/hloc-tests
./run_tests.sh
```

## Test Modes

The `run_tests.sh` script supports multiple modes:

| Mode         | Description                | Example                       |
| ------------ | -------------------------- | ----------------------------- |
| `all`        | Run all tests (default)    | `./run_tests.sh`              |
| `api`        | Run API surface tests only | `./run_tests.sh . api`        |
| `functional` | Run functional tests only  | `./run_tests.sh . functional` |
| `coverage`   | Run with coverage report   | `./run_tests.sh . coverage`   |
| `fast`       | Skip slow tests            | `./run_tests.sh . fast`       |

You can also specify a test target as the first argument:

```bash
./run_tests.sh test_api.py        # Run specific test file
./run_tests.sh test_api.py api    # Run API mode on specific file
```

## Writing New Tests

1. Create test file following naming convention: `test_<name>.py`
2. Import utilities: `from test_utils import setup_hloc_path, print_test_header, print_test_result`
3. Implement test functions using pytest patterns
4. Add pytest markers if needed (`@pytest.mark.slow`, `@pytest.mark.integration`)
5. Tests are automatically discovered by pytest

Example:

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

import sys
from test_utils import setup_hloc_path, print_test_header, print_test_result

def test_my_feature():
    print_test_header("My Feature Test")

    try:
        # Test logic here
        result = True
        print_test_result(result)
        return result
    except Exception as e:
        print_test_result(False, str(e))
        return False

def main():
    try:
        setup_hloc_path()
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1

    passed = test_my_feature()
    return 0 if passed else 1

if __name__ == '__main__':
    sys.exit(main())
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'packaging'`

**Solution**: Run inside Docker container where dependencies are installed

```bash
docker run --rm -it --entrypoint bash scenescape-autocalibration-test:latest
cd /opt/hloc-tests
./run_tests.sh
```

### Test Skipped

**Problem**: Test shows `⚠️ Skipped - dependencies missing`

**Solution**: This is expected if optional dependencies (PIL, model weights) are unavailable. Test will pass with warning.

### All Tests Fail

**Problem**: All tests fail immediately

**Solution**: Ensure you're in the tests directory inside Docker

```bash
# Tests need to be run from the tests directory
cd /opt/hloc-tests  # Inside Docker
./run_tests.sh
```

## See Also

- [./build_test.py](./build_test.py) - Lightweight build-time test
- [../UPGRADE-NOTES.md](../UPGRADE-NOTES.md) - Upgrade documentation
