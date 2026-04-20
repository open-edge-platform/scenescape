# Prerequisites

If you have not already, review the [System Requirements](./system-requirements.md) to ensure your system is compatible with Intel® SceneScape.

## Prerequisite Software

The prerequisite software can be installed via the following commands on the Ubuntu host OS:

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

## Installing Docker on your system

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

## Limitations

During the Docker build process, packages are installed from public repositories. Intel has no control over the public repositories. Specific versions of packages might be removed by the owners at any time, which may break the Docker image build. The Docker build targets the latest available versions of software packages from the public repositories while keeping the same major version.

Between Intel® SceneScape releases, it is possible that packages in public apt repositories get upgraded to newer versions. Although it is possible for these upgraded software packages to work without issues with the latest release, you assume all risks associated with the use of the upgraded packages.

File an issue on github if you encounter a compatibility issue with the latest packages.

## Next Steps

Once these prerequisites are met, proceed to [Get Started](../get-started.md#step-1-get-intel-scenescape) to set up and run Intel® SceneScape.
