# SPDX-License-Identifier: Apache-2.0

# (C) 2025 Intel Corporation

# HLOC Patch Verification Tests

Modular test suite for verifying HLOC patches maintain functional equivalence after upgrading to latest main.

## Test Structure

```
tests/
├── test_utils.py         # Shared test utilities
├── test_api.py          # API surface checks (imports, signatures, classes)
├── test_extraction.py   # Feature extraction functionality
├── test_matching.py     # Feature matching functionality
├── test_matchers.py     # Custom matchers (LoFTR, QTA-LoFTR, dense matching)
├── test_database.py     # COLMAP database operations
├── test_workflows.py    # Reconstruction and pipeline workflows
└── run_tests.py         # Test runner
```

## Running Tests

### All Tests

```bash
# From scenescape root
cd autocalibration
make verify-hloc-patches

# Or directly
cd autocalibration/src/reloc/tests
python3 run_tests.py
```

### API Tests Only (Quick)

```bash
make verify-hloc-api

# Or directly
python3 run_tests.py --api-only
```

### Functional Tests Only

```bash
make verify-hloc-functional

# Or directly
python3 run_tests.py --functional-only
```

### Specific Test

```bash
make verify-hloc-test TEST=api
make verify-hloc-test TEST=extraction
make verify-hloc-test TEST=matching
make verify-hloc-test TEST=matchers
make verify-hloc-test TEST=database
make verify-hloc-test TEST=workflows

# Or directly
python3 run_tests.py --test api
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

- ✅ Creates synthetic test images
- ✅ Extracts keypoints and descriptors
- ✅ Validates H5 output format
- ✅ Verifies descriptor dimensions

**Dependencies**: PIL, numpy, h5py, torch  
**Run Time**: 5-10 seconds

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
docker run --rm -it scenescape-autocalibration:latest bash -c "cd /tmp/reloc && python3 tests/run_tests.py"
```

## Makefile Targets

| Target                         | Description                      |
| ------------------------------ | -------------------------------- |
| `verify-hloc-patches`          | Run all tests (API + functional) |
| `verify-hloc-api`              | Run API surface tests only       |
| `verify-hloc-functional`       | Run functional tests only        |
| `verify-hloc-test TEST=<name>` | Run specific test                |

## Writing New Tests

1. Create test file following naming convention: `test_<name>.py`
2. Import utilities: `from test_utils import setup_hloc_path, print_test_header, print_test_result`
3. Implement test functions
4. Add main() function that runs tests
5. Add to appropriate category in `run_tests.py`

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
docker run --rm -it scenescape-autocalibration:latest bash
cd /tmp/reloc
python3 tests/run_tests.py
```

### Test Skipped

**Problem**: Test shows `⚠️ Skipped - dependencies missing`

**Solution**: This is expected if optional dependencies (PIL, model weights) are unavailable. Test will pass with warning.

### All Tests Fail

**Problem**: All tests fail immediately

**Solution**: Ensure you're in HLOC directory or tests automatically find it

```bash
# Tests need to find hloc/ subdirectory
cd /tmp/reloc  # Inside Docker
python3 tests/run_tests.py
```

## See Also

- [../build_test.py](../build_test.py) - Lightweight build-time test
- [../verify_patches.py](../verify_patches.py) - Original monolithic test (deprecated)
- [../patches/VERIFICATION.md](../patches/VERIFICATION.md) - Comprehensive verification guide
- [../UPGRADE-NOTES.md](../UPGRADE-NOTES.md) - Upgrade documentation
