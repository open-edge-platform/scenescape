
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
    --from tools/dependencies/release-data/SceneScape-1.4.0-deps.csv \
    --deps build/all_dependencies.csv \
    --sbom build/sboms \
    --image-list tools/dependencies/release-data/SceneScape-1.5.0-images.csv \
    --output build/SceneScape-1.5.0-deps.csv

# Optional: Add "New" column to identify new dependencies
python3 tools/dependencies/update_dependencies.py \
    --from tools/dependencies/release-data/SceneScape-1.4.0-deps.csv \
    --deps build/all_dependencies.csv \
    --sbom build/sboms \
    --image-list tools/dependencies/release-data/SceneScape-1.5.0-images.csv \
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

```
python generate_third_party_programs.py
```

Review not found licenses and update the known licenses set accordingly.
TODO: download licenses from SPDX. Use: https://github.com/spdx/license-list-data/tree/main/text

## Limitations

Not covered in the provided automation tools:
- full automation of license identification: for some software packages it may be hard to identify the license automatically. In such cases users need to investigate it on their own.
- the generation of `Dockerfile.source` bundling the sources of all software packages distributed under licenses that requires it.
