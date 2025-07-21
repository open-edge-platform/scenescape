# System Requirements

This page provides detailed hardware, software, and platform requirements to help you set up and run Intel® SceneScape efficiently.

## Supported Platforms

<!--
**Guidelines**:
- Include supported operating systems, versions, and platform-specific notes.
-->

**Operating Systems**

- Ubuntu 24.04 LTS

**Hardware Platforms**

- 10th Gen or newer Intel® Core™ processors (i5 or higher)
- 2nd Gen or newer Intel® Xeon® processors (recommended for large deployments)

## Software Requirements

<!--
**Guidelines**:
- List software dependencies, libraries, and tools.
-->

**Required Software**:

- Docker 24.0 or higher
- git
- curl
- make
- openssl
- unzip

## Limitations

During the Docker build process, packages are installed from public repositories. Intel has no control over the public repositories. Specific versions of packages might be removed by the owners at any time, which may break the Docker image build. The Docker build targets the latest available versions of software packages from the public repositories while keeping the same major version.

Between Intel® SceneScape releases, it is possible that packages in public apt repositories get upgraded to newer versions. Although it is possible for these upgraded software packages to work without issues with the latest release, you assume all risks associated with the use of the upgraded packages.

File an issue on github if you encounter a compatibility issue with the latest packages.

## Validation

- Ensure all dependencies are installed and configured before proceeding to [Get Started](Getting-Started-Guide.md).
