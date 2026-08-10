# System Requirements

This page provides requirements to help you set up and run Scenescape efficiently.

<!--
**Guidelines**:
- Include supported operating systems, versions, and platform-specific notes.
-->

## Hardware Platforms

- 10th Gen or newer Intel® Core™ processors (i5 or higher)
- 2nd Gen or newer Intel® Xeon® processors (recommended for large deployments)

## Operating Systems

- Ubuntu 24.04 LTS

## Required Software

<!--
**Guidelines**:
- List software dependencies, libraries, and tools.
-->

Software dependencies and installation commands for Ubuntu:

::::{grid} 1 1 2 2
:::{grid-item}

- Docker 24.0 or higher
- curl
- git
- make
- openssl
- unzip
- rsync
  :::

:::{grid-item}

```console
sudo apt update
sudo apt install -y \
  curl \
  git \
  make \
  openssl \
  unzip \
  rsync
```

:::
::::

:::::{dropdown} Installing Docker on your system

1. Install Docker using the official installation guide for Ubuntu:
   [Docker Installation Guide for Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

2. Configure Docker to start on boot and add your user to the Docker group:

   ```console
   sudo systemctl enable docker
   sudo usermod -aG docker $USER
   ```

3. Log out and log back in for group membership changes to take effect.

4. Verify Docker is working properly:

   ```console
   docker --version
   docker run hello-world
   ```

**Limitations**

During the Docker build process, packages are installed from public repositories. Intel has no control over the public repositories. Specific versions of packages might be removed by the owners at any time, which may break the Docker image build. The Docker build targets the latest available versions of software packages from the public repositories while keeping the same major version.

Between Scenescape releases, it is possible that packages in public apt repositories get upgraded to newer versions. Although it is possible for these upgraded software packages to work without issues with the latest release, you assume all risks associated with the use of the upgraded packages.

File an issue on GitHub if you encounter a compatibility issue with the latest packages.
:::::
