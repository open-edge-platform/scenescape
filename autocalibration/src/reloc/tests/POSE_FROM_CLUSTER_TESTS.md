# SPDX-FileCopyrightText: (C) 2026 Intel Corporation

# SPDX-License-Identifier: Apache-2.0

# pose_from_cluster Test Suite

Comprehensive functional tests for the `pose_from_cluster` function in `localize_scenescape.py`.

## Overview

The `pose_from_cluster` function is the core localization routine that estimates camera pose from 2D-3D correspondences. These tests verify it handles various scenarios correctly, especially edge cases that can cause crashes.

## Test Coverage

### 1. Signature and Parameter Tests

**Test**: `test_pose_from_cluster_signature`

- Verifies function has expected parameters in correct order
- Ensures API stability across HLOC versions

**Test**: `test_pose_from_cluster_parameters_types`

- Checks default values: `skip=0`, `match_dense=False`, `depth_scale=1.0`, `depth_max=9.9`
- Validates parameter types match expectations

### 2. Empty Array Handling

**Test**: `test_pose_from_cluster_empty_arrays`

- **Purpose**: Prevents the `'NoneType' object does not support item assignment` error
- **Scenario**: All matches are filtered out (invalid depth data)
- **Expected**: Returns `{'success': False}` with empty arrays
- **Critical**: This test catches the bug we just fixed where `pycolmap.absolute_pose_estimation()` returns `None` for empty arrays

**Mock Data**:

- Feature file with 10 keypoints per image
- Match file with all matches set to -1 (no valid matches)
- PLY depth file (empty mesh)

### 3. Too Few Matches

**Test**: `test_pose_from_cluster_too_few_matches`

- **Purpose**: Verifies failure when matches ≤ 4 (insufficient for pose estimation)
- **Scenario**: Only 3 valid matches (below RANSAC minimum)
- **Expected**: Returns `{'success': False, 'cfg': query_intrinsics}`

**Mock Data**:

- 3 keypoints and 3 matches (below threshold)
- Should fail before calling `absolute_pose_estimation`

### 4. Valid Depth Data

**Test**: `test_pose_from_cluster_with_valid_depth_data`

- **Purpose**: Verifies successful processing with valid 3D points
- **Scenario**: PNG depth file with non-zero depth values
- **Expected**: Returns valid result structure with 3D points

**Mock Data**:

- 50 keypoints per image, 20 matches
- PNG depth image (480x640) with depth value 1000 (scaled to 1.0m)
- Uses `depth_scale=1000.0` to convert to meters

**Limitations**:

- Full pose estimation may still fail if 3D points lack variation
- Test focuses on data flow and structure validation

### 5. Dense Matching Mode

**Test**: `test_pose_from_cluster_dense_matching`

- **Purpose**: Verifies dense matching path (different data format)
- **Scenario**: Match file stores keypoints directly instead of match indices
- **Expected**: Completes without error, returns valid structure

**Mock Data**:

- Dense match file with `keypoints0` and `keypoints1` arrays
- `match_dense=True` parameter

## Running Tests

### Run All pose_from_cluster Tests

```bash
cd autocalibration/src/reloc/tests
pytest test_localize_scenescape.py::TestPoseFromCluster -v
```

### Run Specific Test

```bash
pytest test_localize_scenescape.py::TestPoseFromCluster::test_pose_from_cluster_empty_arrays -v
```

### Run with Coverage

```bash
pytest test_localize_scenescape.py::TestPoseFromCluster --cov=hloc.pipelines.SceneScape.localize_scenescape --cov-report=term-missing
```

### Manual Test Runner

```bash
python3 test_pose_from_cluster_manual.py
```

## Why These Tests Matter

### Bug Prevention

The empty array test (`test_pose_from_cluster_empty_arrays`) directly tests the bug we encountered:

```python
# Bug: This crashes when all matches are filtered out
all_mkpq = np.concatenate(all_mkpq, 0)  # Shape: (0, 2)
all_mkp3d = np.concatenate(all_mkp3d, 0)  # Shape: (0, 3)
ret = pycolmap.absolute_pose_estimation(...)  # Returns None
ret["cfg"] = query_intrinsics  # ❌ NoneType error!

# Fix: Check for empty arrays
if len(all_mkpq) == 0 or len(all_mkp3d) == 0:
    return {'success': False, 'cfg': query_intrinsics}, [], [], [], [], 0
```

### pycolmap 0.5.0 Compatibility

These tests verify the pycolmap API changes are handled correctly:

- Camera object creation from dict
- Points format (list of column vectors)
- Estimation options structure

### Regression Detection

When upgrading HLOC or pycolmap in the future, these tests will catch:

- API signature changes
- Behavior changes in edge cases
- Return value structure modifications

## Test Data Structure

### Feature Files (HDF5)

```
features.h5
├── query.jpg/
│   └── keypoints: (N, 2) float32
└── db_001.jpg/
    └── keypoints: (N, 2) float32
```

### Match Files (HDF5)

**Sparse Matching**:

```
matches.h5
└── query.jpg/db_001.jpg/
    └── matches0: (N,) int32  # Index into db keypoints (-1 = no match)
```

**Dense Matching**:

```
matches_dense.h5
└── query.jpg/db_001.jpg/
    ├── keypoints0: (M, 2) float32
    └── keypoints1: (M, 2) float32
```

### Depth Files

- **PLY**: Empty mesh (for testing empty case)
- **PNG**: 16-bit depth image (480x640, value 1000 = 1.0m with scale=1000)

### Retrieval Calibration

```python
{
    "db_001.jpg": SimpleNamespace(
        depth_name="depth.png",
        qvec=np.array([1.0, 0.0, 0.0, 0.0]),  # Identity rotation
        tvec=np.array([0.0, 0.0, 0.0]),       # Zero translation
        intrinsics={'model': 'SIMPLE_PINHOLE', 'width': 640, 'height': 480, 'params': [500.0, 320.0, 240.0]}
    )
}
```

## Future Enhancements

### Additional Test Cases

1. **Multiple Retrieved Images**: Test with 5+ database images
2. **Invalid Camera Intrinsics**: Test error handling for malformed camera params
3. **Corrupted Depth Files**: Test handling of I/O errors
4. **Large Scale Tests**: Test with 1000+ keypoints
5. **Real Depth Data**: Test with actual mesh/PNG depth from sample datasets

### Integration Tests

1. **End-to-End Localization**: Full pipeline from image to pose
2. **Multiple Depth Formats**: Test .ply, .stl, .obj, .png, .h5 depth files
3. **Coordinate Transform Validation**: Verify world/camera coordinate conversions
4. **RANSAC Validation**: Test inlier/outlier handling

### Performance Tests

1. **Benchmark**: Measure execution time vs. number of matches
2. **Memory**: Track memory usage with large feature sets
3. **Scalability**: Test with varying database sizes

## Related Files

- **Implementation**: `autocalibration/src/reloc/new-files/hloc/pipelines/SceneScape/localize_scenescape.py`
- **Main Tests**: `autocalibration/src/reloc/tests/test_localize_scenescape.py`
- **Manual Runner**: `autocalibration/src/reloc/tests/test_pose_from_cluster_manual.py`
- **Patches**: `autocalibration/src/reloc/patches/05-pycolmap-api-fix.patch`, `06-pycolmap-rigid3d-api.patch`

## Debugging Failed Tests

### Test Fails with Import Error

```bash
# Ensure HLOC is in Python path
export PYTHONPATH=/tmp/reloc:$PYTHONPATH
pytest test_localize_scenescape.py::TestPoseFromCluster -v
```

### Test Fails with Missing Dependencies

```bash
pip install pytest h5py pillow scipy open3d-cpu pycolmap
```

### Test Fails with "Cannot create camera"

Check that pycolmap version ≥ 0.5.0:

```bash
python3 -c "import pycolmap; print(pycolmap.__version__)"
```

### Enable Debug Logging

The implementation has extensive debug logging. To see it:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
# Run test
```

## Conclusion

This test suite provides confidence that `pose_from_cluster` handles edge cases correctly and is compatible with pycolmap 0.5.0. The tests catch the critical empty array bug and verify all API changes are properly implemented.
