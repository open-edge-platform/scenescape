<!--
SPDX-License-Identifier: Apache-2.0
(C) 2025 Intel Corporation
-->

# HLOC Patch Verification Guide

This guide explains how to verify that the patched HLOC implementation maintains functional equivalence after upgrading to the latest main branch.

## Quick Verification (Patch Application Only)

Test that patches apply cleanly to latest HLOC:

```bash
# Clone latest HLOC
git clone https://github.com/cvg/Hierarchical-Localization.git /tmp/hloc-test
cd /tmp/hloc-test

# Apply patches
for patch in /path/to/scenescape/autocalibration/src/reloc/patches/*.patch; do
    patch -p0 < "$patch" || exit 1
done

# Copy new files
cp -r /path/to/scenescape/autocalibration/src/reloc/new-files/* .

echo "✅ Patches applied successfully"
```

## Comprehensive Verification (With Dependencies)

### Option 1: Within Docker Container

The most reliable way to test is within the built Docker container where all dependencies are installed:

```bash
# Build the autocalibration image
cd /path/to/scenescape
make rebuild-autocalibration

# Run verification inside container
docker run -it --rm scenescape-autocalibration:latest bash -c "cd /tmp/reloc && python3 /path/to/verify_patches.py"
```

### Option 2: Local Python Environment

Install dependencies first:

```bash
cd /tmp/hloc-test  # Patched HLOC directory

# Install HLOC dependencies
pip install -r requirements.txt
pip install packaging numpy torch torchvision h5py pillow

# Run verification
python3 /path/to/scenescape/autocalibration/src/reloc/verify_patches.py
```

### Option 3: API Checks Only

Skip functional tests if dependencies are not available:

```bash
python3 verify_patches.py --api-only
```

## Verification Test Levels

The `verify_patches.py` script performs multiple levels of testing:

### Level 1: API Surface Checks

- ✅ Module imports (core HLOC and custom SceneScape modules)
- ✅ Function signatures (main entry points)
- ✅ Class existence (custom matchers: LoFTR, QTA-LoFTR)

### Level 2: Functional Tests

- ✅ **Feature Extraction**: Creates synthetic images, extracts keypoints/descriptors
- ✅ **Feature Matching**: Tests matching between image pairs
- ✅ **Dense Matching**: Verifies match_dense module (custom)
- ✅ **Custom Matchers**: Tests LoFTR and QTA-LoFTR instantiation
- ✅ **Database Operations**: Tests COLMAP database creation and queries
- ✅ **Reconstruction Workflow**: Verifies reconstruction and triangulation APIs
- ✅ **SceneScape Pipeline**: Tests custom pipeline utilities

## Expected Output

### Successful Verification

```
================================================================================
HLOC Patch Verification
================================================================================

PART 1: API SURFACE CHECKS
================================================================================
✅ All modules import successfully
✅ All function signatures match expected
✅ All custom classes exist

PART 2: FUNCTIONAL TESTS
================================================================================
✅ Feature Extraction test passed
✅ Feature Matching test passed
✅ Dense Matching test passed
✅ Custom Matchers test passed
✅ Database Operations test passed
✅ Reconstruction Workflow test passed
✅ SceneScape Pipeline test passed

================================================================================
✅ ALL VERIFICATION CHECKS PASSED
================================================================================
```

### Critical: DoG Extractor API Test

The DoG (SIFT) extractor test is particularly important as it validates pycolmap API compatibility:

```
DoG Extractor API
  Creating test image...
  Instantiating DoG extractor...
  Testing forward pass...
  ✓ Extracted 128 keypoints
  ✓ Output structure valid
✅ PASSED
```

**Why this test matters**: pycolmap >=0.5.0 changed `Sift.extract()` return signature from 3 values `(keypoints, scores, descriptors)` to 2 values `(keypoints, descriptors)`. Without the fix in patch `05-pycolmap-api-fix.patch`, this causes runtime error:

```python
ValueError: not enough values to unpack (expected 3, got 2)
```

This test catches such API mismatches at build time, preventing runtime failures during camera calibration.

### Acceptable Warnings

Some warnings (⚠️) are acceptable:

- `⚠️ LoFTR instantiation skipped (weights not available)` - Model weights not downloaded
- `⚠️ Skipping full workflow test (requires complete dataset)` - Full dataset not present
- `⚠️ SceneScape pipeline missing main/run function` - Optional pipeline feature

These warnings indicate optional features that don't affect core functionality.

## Integration Testing

After verification, test with actual calibration workflows:

### Test 1: Camera Calibration Pipeline

```bash
# Inside SceneScape environment
cd /path/to/scenescape

# Run basic acceptance tests
make run_basic_acceptance_tests

# Check for autocalibration-specific tests
make -C tests unit-tests
```

### Test 2: Visual Inspection

Compare outputs from old vs new versions:

1. Run calibration on same input data
2. Compare camera intrinsics (focal length, principal point)
3. Compare camera extrinsics (rotation, translation)
4. Verify feature matching quality visually

### Test 3: Regression Testing

Use known-good calibration datasets:

```bash
# Save reference outputs from old version
./run_calibration.sh dataset1 > old_results.txt

# Rebuild with new patches
make rebuild-autocalibration

# Compare outputs
./run_calibration.sh dataset1 > new_results.txt
diff old_results.txt new_results.txt
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'packaging'`

**Solution**: Install dependencies or run inside Docker container

```bash
pip install packaging torch numpy h5py pillow
```

### Patch Application Failures

**Problem**: `patch: **** malformed patch at line X`

**Solution**: Patches may be out of sync with latest HLOC

1. Check HLOC commit: `git log -1 --oneline`
2. Compare with [UPGRADE-NOTES.md](../UPGRADE-NOTES.md) - should be c13273bd or later
3. If HLOC has advanced significantly, regenerate patches (see [README.md](README.md))

### Test Failures

**Problem**: Functional tests fail with errors

**Solution**: Check dependencies and model weights

1. Ensure all requirements installed: `pip install -r requirements.txt`
2. Check PyTorch installation: `python -c "import torch; print(torch.__version__)"`
3. For matcher tests, model weights may be required

### Performance Issues

**Problem**: Tests run slowly

**Solution**: Use `--api-only` flag for quick checks

```bash
python3 verify_patches.py --api-only  # Skip functional tests
```

## Continuous Integration

For CI/CD pipelines, add verification to test suite:

```yaml
# .github/workflows/test.yml
- name: Verify HLOC Patches
  run: |
    cd autocalibration/src/reloc
    docker run scenescape-autocalibration:latest \
      python3 /tmp/reloc/verify_patches.py
```

## Reporting Issues

If verification fails:

1. **Capture full output**: `python3 verify_patches.py > verify.log 2>&1`
2. **Check HLOC version**: `git log -1 --oneline` inside HLOC directory
3. **Review failure details**: Look for specific test that failed
4. **Check dependencies**: Verify all requirements installed
5. **Report**: Include verify.log, HLOC commit, and error details

## See Also

- [README.md](README.md) - Patch organization and application
- [../UPGRADE-NOTES.md](../UPGRADE-NOTES.md) - Upgrade history and details
- [../../docs/README.md](../../../docs/README.md) - Autocalibration documentation
- [../../Agents.md](../../../Agents.md) - AI agent instructions
