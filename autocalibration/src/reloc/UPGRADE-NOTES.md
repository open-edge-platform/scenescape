# HLOC Upgrade and pycolmap 4.0.4 Alignment

## Patch Updates

All 7 patches apply to hloc commit `c13273b` and align the Scenescape-specific
changes with `pycolmap==4.0.4`:

| Patch                             | Old Size         | New Size         | Description                                |
| --------------------------------- | ---------------- | ---------------- | ------------------------------------------ |
| 00-top-level-files.patch          | 134 lines        | 236 lines        | LICENSE, README, requirements, setup.py    |
| 01-core-modifications.patch       | 6,941 lines      | 7,821 lines      | Core hloc modules                          |
| 02-extractors-modifications.patch | 834 lines        | 966 lines        | Feature extractors                         |
| 03-matchers-modifications.patch   | 391 lines        | 554 lines        | Feature matchers                           |
| 04-pipelines-modifications.patch  | 1,738 lines      | 2,105 lines      | Pipeline examples                          |
| 05-pycolmap-api-fix.patch         | N/A              | 17 lines         | Fix SIFT extractor return format           |
| 06-pycolmap-rigid3d-api.patch     | N/A              | 33 lines         | Replace qvec/rotmat conversions with SciPy |
| **Total**                         | **10,038 lines** | **11,732 lines** | pycolmap 4.0.4 aligned                     |

## Migration Impact

### pycolmap 4.0.4 API alignment

- Pose estimation uses `estimate_and_refine_absolute_pose`.
- Pose-estimation inputs use `pycolmap.Camera` and contiguous NumPy arrays.
- RANSAC options use `AbsolutePoseEstimationOptions`.
- The upstream `QueryLocalizer` implementation is preserved rather than
  overriding it with a second pose-estimation implementation.
- SIFT return-value and `Rigid3d` conversion changes are handled by patches 05
  and 06.

### Preserved Scenescape-specific modifications

- Custom matchers (LoFTR, QTA-LoFTR)
- Scenescape pipeline integrations
- Utility functions (dataset.py, evaluate.py)
- Configuration files (setup.cfg)

### Benefits

- Latest bug fixes and performance improvements from upstream
- Better pycolmap integration
- Improved error handling
- No maintenance burden from pinned commit
