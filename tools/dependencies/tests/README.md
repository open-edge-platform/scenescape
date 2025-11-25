# Testing for generate_third_party_programs.py

This directory contains comprehensive tests for the `generate_third_party_programs.py` script.

## Test Files

### Main Test Script
- `test_generate_third_party_programs.py` - Main unit test suite with comprehensive test cases

### Demo Script  
- `demo_generate_third_party.py` - Interactive demonstration using test data

### Test Data
- `test_data/` - Directory containing sample input files and expected outputs
  - `simple_deps.csv` - Simple dependencies with common licenses
  - `complex_deps.csv` - Complex dependencies with multiple/compound licenses
  - `test_preamble.txt` - Sample preamble file
  - `licenses/` - Local license files for testing
    - `MIT.txt` - MIT license text
    - `BSD-3-Clause.txt` - BSD 3-Clause license text

## Running Tests

### Run All Unit Tests
```bash
cd tools/dependencies
python3 tests/test_generate_third_party_programs.py
```

### Run Demo with Test Data
```bash
cd tools/dependencies  
python3 tests/demo_generate_third_party.py
```

### Run Individual Test with pytest (if available)
```bash
cd tools/dependencies
python3 -m pytest tests/test_generate_third_party_programs.py -v
```

## Test Coverage

The test suite covers:

1. **License URL Mapping** - Tests the SPDX license URL mapping functionality
2. **Filename Sanitization** - Tests safe filename generation from license names
3. **License Text Download** - Tests downloading from SPDX and fallback to local files
4. **Dependency Processing** - Tests CSV parsing and license extraction
5. **Multiple License Handling** - Tests components with "and", "or", "OR" license combinations  
6. **Empty License Handling** - Tests behavior with missing license information
7. **Main Function** - Tests command-line argument parsing and execution
8. **Error Handling** - Tests missing input files and error conditions

## Test Data Explanation

### simple_deps.csv
Contains 5 components with 2 different licenses (BSD-3-Clause, Apache-2.0):
- Tests basic functionality with well-known licenses
- All licenses should be downloadable from SPDX

### complex_deps.csv  
Contains 4 components with compound license expressions:
- `Artistic License or GPL-1.0` - Tests "or" separator
- `MIT and Apache-2.0` - Tests "and" separator  
- `BSD-3-Clause OR MIT` - Tests "OR" separator (uppercase)
- Tests license parsing edge cases

## Golden Reference

The main `third-party-programs.txt` file in the repository root serves as a golden reference output generated from `SceneScape-1.4.0-Dependencies.csv`. The tests use smaller, simpler examples to verify individual functionality components rather than testing against the full dataset.

## Expected Test Behavior

- **Network Tests**: Most tests mock network requests to avoid dependencies on external services
- **File I/O Tests**: Use temporary directories to avoid affecting the main repository
- **License Downloads**: Tests both successful downloads and fallback to local files
- **Error Conditions**: Verify proper error handling and user messages

## Adding New Tests

To add new test cases:

1. Add test methods to `TestGenerateThirdPartyPrograms` class
2. Use the `setUp()` and `tearDown()` methods for test isolation
3. Create new test data files in `test_data/` if needed
4. Mock external dependencies (network, file system) as appropriate
5. Follow the existing naming convention: `test_<functionality>_<scenario>`