# HLOC Patches for SceneScape

This directory contains patches to be applied to the upstream HLOC repository (latest main branch).

Patches were last regenerated against HLOC commit `c13273bd0ecc2917a35910fd843712a1c6243193` (December 10, 2025).

## Quick Start

```bash
# Clone HLOC from main branch
git clone https://github.com/cvg/Hierarchical-Localization.git reloc
cd reloc

# Apply all patches
for patch in patches/*.patch; do
    patch -p0 < "$patch"
done

# Copy new files
cp -r new-files/* .
```

## Patch Organization

Patches are organized logically by functionality and must be applied in numerical order:

1. **00-top-level-files.patch** - Updates LICENSE, README.md, requirements.txt, setup.py
2. **01-core-modifications.patch** - Core hloc module changes (utils, main modules)
3. **02-extractors-modifications.patch** - Feature extractor modifications
4. **03-matchers-modifications.patch** - Feature matcher modifications
5. **04-pipelines-modifications.patch** - Modifications to existing pipeline examples

### Patch Format

All patches use `-p0` format (paths relative to repository root):

```
--- hloc/some_file.py
+++ hloc/some_file.py
```

## New Files

Files in `new-files/` are entirely new and not present in upstream HLOC:

- `setup.cfg` - Python package configuration
- `hloc/match_dense.py` - Dense matching functionality
- `hloc/matchers/loftr.py` - LoFTR matcher implementation
- `hloc/matchers/qta_loftr.py` - QTA-LoFTR matcher
- `hloc/utils/dataset.py` - Dataset loading utilities
- `hloc/utils/evaluate.py` - Evaluation metrics
- `hloc/pipelines/utils.py` - Pipeline utilities
- `hloc/pipelines/SceneScape/` - SceneScape-specific localization pipeline

## Dockerfile Integration

The autocalibration Dockerfile applies these patches during the build:

```dockerfile
# Copy patches and new files
COPY autocalibration/reloc-patches /tmp/reloc-patches
COPY autocalibration/reloc-new-files /tmp/reloc-new-files

# Clone and patch hloc
RUN git clone https://github.com/cvg/Hierarchical-Localization.git /tmp/reloc && \
    cd /tmp/reloc && \
    git checkout 4961d117b4290e97b03120c54694224a823e7e04 && \
    patch -p0 < /tpatches/00-top-level-files.patch && \
    patch -p0 < /tpatches/01-core-modifications.patch && \
    patch -p0 < /tpatches/02-extractors-modifications.patch && \
    patch -p0 < /tpatches/03-matchers-modifications.patch && \
    patch -p0 < /tpatches/04-pipelines-modifications.patch && \
    cp -r /tnew-files/* /tmp/reloc/ && \
    rm -rf /tmp/reloc/.git
```

## Verification

To verify the patches produce the correct output:

```bash
# After applying patches and copying new files
cd /tmp
diff -qr reloc /path/to/scenescape/autocalibration/src/reloc \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='datasets' --exclude='demo.ipynb' --exclude='doc' \
    --exclude='Dockerfile' --exclude='.git*' \
    --exclude='4Seasons' --exclude='7Seasons' --exclude='Aachen' \
    --exclude='Aachen_v1_1' --exclude='Cambridge' --exclude='CMU' \
    --exclude='InLoc' --exclude='RobotCar' \
    --exclude='pairs' --exclude='pipeline_*.ipynb' --exclude='third_party'
```

No output means the directories are identical (success).

## Verification

After applying patches, verify functionality:

### Quick Check (Build Time)

```bash
cd /path/to/patched-hloc
python3 /path/to/scenescape/autocalibration/src/reloc/build_test.py
```

This tests basic imports and API surface - runs automatically during Docker build.

### Comprehensive Check (With Dependencies)

```bash
cd /path/to/patched-hloc
python3 /path/to/scenescape/autocalibration/src/reloc/verify_patches.py
```

This performs functional tests including:

- Feature extraction with synthetic images
- Feature matching workflows
- Custom matcher validation
- Database operations
- Reconstruction pipelines

**See [VERIFICATION.md](VERIFICATION.md) for detailed verification guide.**

## Maintenance

When updating to a newer HLOC commit:

1. Clone the new HLOC commit
2. Regenerate patches by comparing with current reloc:
   ```bash
   cd autocalibration/src/reloc
   diff -Naur /path/to/new-hloc/file file > ../patches/new.patch
   ```
3. Test patches apply cleanly
4. Run verification tests
5. Update commit hash in this documentation
