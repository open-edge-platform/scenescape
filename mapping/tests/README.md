# Mapping Module Unit Tests

This directory contains unit tests for the SceneScape mapping module. The tests are designed to run inside the mapping container where all dependencies and models are already initialized.

## Quick Start

```bash
# 1. Enter the mapping container
docker exec -it mapping-test bash

# 2. Navigate to tests directory
cd /workspace/mapping/tests

# 3. Run all tests
pytest -v

# OR use the test runner script
./run_tests.sh
```

**Note**: Test dependencies are pre-installed in the `mapping-test` container.

## Overview

The test suite covers:

- **Model Interface** (`test_model_interface.py`): Tests for the abstract base class and helper methods
- **Mesh Utilities** (`test_mesh_utils.py`): Tests for mesh and point cloud processing functions
- **API Service** (`test_api_service.py`): Tests for Flask API endpoints (multipart/form-data) and request validation
- **Fixtures** (`conftest.py`): Shared test fixtures and configuration

| File                      | What It Tests                      | Test Count |
| ------------------------- | ---------------------------------- | ---------- |
| `test_model_interface.py` | Base class methods and utilities   | 20+        |
| `test_mesh_utils.py`      | Mesh and point cloud processing    | 14+        |
| `test_api_service.py`     | Flask API endpoints and validation | 25+        |
| **Total**                 |                                    | **59+**    |

**Note**: API tests use multipart/form-data format to match the production API which accepts file uploads for both images and videos.

## Prerequisites

These tests are designed to run **inside a running mapping container** because:

1. Model dependencies (MapAnything, VGGT, etc.) are complex and require specific environments
2. The container has all required packages pre-installed
3. Model weights and configurations are already in place
4. Test dependencies are pre-installed in the `mapping-test` container image

## Running the Tests

### Quick Commands

```bash
# All unit tests
pytest -v

# Single test file
pytest test_model_interface.py -v

# Single test function
pytest test_model_interface.py::TestReconstructionModel::test_model_initialization -v

# Fast tests only (skip slow ones)
pytest -v -m "not slow"

# With coverage report
pytest --cov=../src --cov-report=html --cov-report=term

# View coverage in browser (from host machine)
python -m http.server 8000 --directory htmlcov
```

### Using the Test Runner Script

```bash
# All unit tests (default)
./run_tests.sh

# Specific test file
./run_tests.sh test_model_interface.py

# With coverage report
./run_tests.sh . coverage

# Only fast tests
./run_tests.sh . fast

# All tests including integration
./run_tests.sh . all
```

### Detailed Setup (First Time)

#### Step 1: Start the Mapping Container

First, ensure you have a mapping container running. For example:

```bash
# From the scenescape root directory
docker-compose up -d mapping-test
```

Or if you're using a specific model service:

```bash
# For MapAnything
docker-compose up -d mapanything-service

# For VGGT
docker-compose up -d vggt-service
```

#### Step 2: Enter the Container

Open a bash shell inside the running container:

```bash
# For the test container
docker exec -it mapping-test bash

# Or for a specific service
docker exec -it <container-name> bash
```

#### Step 3: Navigate to the Tests Directory

```bash
cd /workspace/mapping/tests
```

#### Step 4: Run the Tests

See [Quick Commands](#quick-commands) above for various ways to run tests.

**Note**: All test dependencies are pre-installed in the container image.

## Test Structure

All tests are **unit tests** that test individual components in isolation using mocks where appropriate. Each test file follows this structure:

```python
import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Import modules to test
from model_interface import ReconstructionModel

class TestClassName:
    """Test suite for ClassName"""

    def test_feature_name(self):
        """Test description"""
        # Arrange
        # Act
        # Assert
```

## Troubleshooting

### "pytest: command not found"

This should not happen in the `mapping-test` container as pytest is pre-installed. If you see this error, verify you're in the correct container:

```bash
docker exec -it mapping-test bash
pytest --version
```

### Import errors

Make sure you're in the container:

```bash
docker exec -it mapping-test bash
cd /workspace/mapping/tests
```

### Want to see print statements

```bash
pytest -v -s
```

### Tests taking too long

```bash
pytest -v -m "not slow" --maxfail=1
```

### Import Errors

If you see import errors for test modules:

**Solution**: Test dependencies are pre-installed in the `mapping-test` container. Ensure you're in the correct container and working directory.

### Model Not Found

If tests fail with "Model not registered" errors:

**Solution**: The unit tests mock models and should not require actual model loading. Check that you're running the correct test file.

### CUDA/GPU Errors

If you see CUDA-related errors:

**Solution**: Tests are designed to run on CPU. Ensure the `device` parameter is set to "cpu" in test fixtures.

### Permission Denied

If you can't write test results or coverage reports:

**Solution**: Run tests from a writable directory:

```bash
cd /tmp
pytest /workspace/mapping/tests -v
```

## Writing New Tests

When adding new tests:

1. Create test file with `test_` prefix: `test_new_module.py`
2. Create test classes with `Test` prefix: `class TestNewModule`
3. Create test functions with `test_` prefix: `def test_new_feature(self)`
4. Use fixtures from `conftest.py` for common test data
5. Use descriptive names and docstrings
6. Follow the Arrange-Act-Assert pattern

Example:

```python
def test_model_initialization(self):
    """Test that model initializes with correct attributes"""
    # Arrange & Act
    model = MockReconstructionModel(device="cpu")

    # Assert
    assert model.device == "cpu"
    assert model.is_loaded is False
```

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```bash
# In your CI script
docker exec mapping-test bash -c "cd /workspace/mapping/tests && pytest -v --junitxml=test-results.xml"
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [pytest Markers](https://docs.pytest.org/en/stable/mark.html)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

## Test Statistics

- **Total Test Files**: 3
- **Total Test Cases**: 59+
- **Execution Time**: <30 seconds
- **Coverage Target**: >80%

## Contact

For questions or issues with the tests, please contact the SceneScape development team or open an issue in the repository.
