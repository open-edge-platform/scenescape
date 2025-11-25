
# How-to use tools for the generation of reports and artifacts related to Open Source Software distributing and licensing

## Generate single CSV file with all dependencies

Prerequisite (run in the top level folder):

```bash
make build-all
make list-dependencies
```

To generate a single CSV file containing all dependencies from all images:

```bash
python3 tools/dependencies/generate_dependencies.py build -o build/all_dependencies.csv
```

This script:
- Scans the build folder for files matching `*-apt-deps.txt` and `*-pip-deps.txt` patterns
- Parses Ubuntu (APT) dependencies and converts them to format: `image,package:version,Ubuntu`
- Parses Python (pip) dependencies and converts them to format: `image,package==version,pypi`
- Outputs a CSV file with header: `Image,Component,Origin`

## Generation of SBOM from Dockerfiles using Docker buildkit

This should generate additional licence information that can be associated with dependencies per Dockerfile
Scripts are provided that generate SBOMS in Json format

```sh
docker buildx create --use --name=scenescape-buildkit-container --driver=docker-container --driver-opt=env.http_proxy=$http_proxy,env.https_proxy=$https_proxy,env.HTTP_PROXY=$HTTP_PROXY,env.HTTPS_PROXY=$HTTPS_PROXY,default-load=true

make generate-sboms

docker buildx rm scenescape-buildkit-container
```

Docs: https://www.docker.com/blog/generate-sboms-with-buildkit/

## Updating dependency list for the current version

Pre-requisite: Check if any Dockerfiles have been renamed/moved and update the previous-release.csv accordingly.

**Important**: Run this script from the repository root directory so it can properly access Dockerfile paths.

```bash
# Run from repository root directory
python3 tools/dependencies/update_dependencies.py \
    --from tools/dependencies/release-data/SceneScape-1.4.0-Dependencies.csv \
    --deps build/all_dependencies.csv \
    --sbom build/sboms \
    --image-list tools/dependencies/release-data/SceneScape-2025.2-Images.csv \
    --output build/SceneScape-1.5.0-deps.csv

# Optional: Add "New" column to identify new dependencies
python3 tools/dependencies/update_dependencies.py \
    --from tools/dependencies/release-data/SceneScape-1.4.0-Dependencies.csv \
    --deps build/all_dependencies.csv \
    --sbom build/sboms \
    --image-list tools/dependencies/release-data/SceneScape-2025.2-Images.csv \
    --output build/SceneScape-1.5.0-deps.csv \
    --show-new
```

This script:
- Compares previous release dependencies with current build dependencies
- Implements 6-rule dependency matching algorithm (exact match, version update, cross-image reuse, etc.)
- Automatically resolves licenses from SBOM data
- Sets "Distributed by you?" field based on image publication status in image list
- Extracts and adds base image dependencies from Dockerfiles
- Provides comprehensive logging and action guidance

For detailed usage, input formats, processing rules, and examples, see: [UPDATE_DEPENDENCIES.md](UPDATE_DEPENDENCIES.md)

## Generate 3-rd party programs file from the reviewed dependency list .csv

The script now supports proper command-line arguments for input/output files:

```bash
# Basic usage - specify input CSV file
python3 generate_third_party_programs.py reviewed_dependencies.csv

# Specify custom output file
python3 generate_third_party_programs.py reviewed_dependencies.csv -o custom_third_party_programs.txt

# Use custom preamble and licenses directory
python3 generate_third_party_programs.py reviewed_dependencies.csv \
    --preamble custom_preamble.txt \
    --licenses-dir custom_licenses_dir
```

### Enhanced License Text Acquisition

The script features an improved license acquisition system:

1. **Primary Source**: Downloads license texts from the official SPDX license repository:
   - `https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/text/`
   - Provides the most up-to-date and authoritative license texts

2. **Auto-Discovery**: For licenses not in the predefined mapping, automatically attempts to find them in the SPDX repository using intelligent name matching. The custom mapping is minimized to only include licenses that require specific SPDX identifier translation (e.g., "BSD License" → "BSD-3-Clause.txt", "PIL" → "HPND.txt")

3. **Local Fallback**: Falls back to local license files in the `licenses/` directory for custom or non-standard licenses

4. **Special License Handling**: Recognizes special license types like "Public Domain" and "collection of licenses" and provides appropriate explanatory text

### Features

The script:
- Takes a reviewed dependencies CSV file with Component and License columns
- Automatically downloads license texts from SPDX when available
- Supports auto-discovery of licenses not in the predefined mapping
- Handles special license types (Public Domain, collection of licenses) with explanatory text
- Falls back to local license files for custom licenses
- Provides detailed output showing license sources and any missing licenses
- Generates a comprehensive third-party programs file with all license texts

### Local License Directory

The `licenses/` directory now contains only custom/non-standard licenses:
- `Bitstream_Vera_License.txt` - Bitstream Vera fonts license
- `Intel_End_User_License.txt` - Intel proprietary software license
- `Intel_Simplified_Software_License.txt` - Intel simplified license
- `The_Regents_of_The_University_of_Michigan.txt` - University of Michigan license
- `ad-hoc.txt` - Custom ad-hoc license text
- `preamble.txt` - Template preamble for the third-party programs file

Standard open-source licenses (MIT, Apache, GPL, LGPL, etc.) are automatically downloaded from the SPDX repository and no longer need local copies.

Review not found licenses and update the local licenses directory accordingly.

## Limitations

Not covered in the provided automation tools:
- full automation of license identification: for some software packages it may be hard to identify the license automatically. In such cases users need to investigate it on their own.
- the generation of `Dockerfile.source` bundling the sources of all software packages distributed under licenses that requires it.
