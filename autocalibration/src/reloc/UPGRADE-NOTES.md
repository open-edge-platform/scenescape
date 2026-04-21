# HLOC Upgrade to Latest Main

## Patch Updates

All 7 patches regenerated to apply cleanly on latest main with pycolmap 0.6.0 compatibility:

| Patch                             | Old Size         | New Size         | Description                                               |
| --------------------------------- | ---------------- | ---------------- | --------------------------------------------------------- |
| 00-top-level-files.patch          | 134 lines        | 236 lines        | LICENSE, README, requirements (pycolmap==0.6.0), setup.py |
| 01-core-modifications.patch       | 6,941 lines      | 7,821 lines      | Core hloc modules                                         |
| 02-extractors-modifications.patch | 834 lines        | 966 lines        | Feature extractors                                        |
| 03-matchers-modifications.patch   | 391 lines        | 554 lines        | Feature matchers                                          |
| 04-pipelines-modifications.patch  | 1,738 lines      | 2,105 lines      | Pipeline examples                                         |
| 05-pycolmap-api-fix.patch         | N/A              | 17 lines         | Fix SIFT extractor for pycolmap >=0.6.0 return format     |
| 06-pycolmap-rigid3d-api.patch     | N/A              | 33 lines         | Replace pycolmap qvec/rotmat conversions with scipy       |
| **Total**                         | **10,038 lines** | **11,732 lines** | +17% increase, pycolmap 0.6.0 ready                       |

## Migration Impact

### Breaking Changes

**None** - All SceneScape-specific modifications preserved:

- Custom matchers (LoFTR, QTA-LoFTR)
- SceneScape pipeline integrations
- Utility functions (dataset.py, evaluate.py)
- Configuration files (setup.cfg)

### Benefits

- Latest bug fixes and performance improvements from upstream
- Better pycolmap integration
- Improved error handling
- No maintenance burden from pinned commit
