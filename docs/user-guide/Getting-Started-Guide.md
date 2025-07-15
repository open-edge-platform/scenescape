# Getting Started with Intel® SceneScape

- **Time to Complete:** 30-45 minutes

## Get Started

### Prerequisites

Check [System Requirements](system-requirements.md) before proceeding with rest of the steps in this documentation.

### Step 1: Install Prerequisites

The prerequisite software can be installed via the following commands on an Ubuntu 22.04 host OS:

```console
sudo apt update
sudo apt install -y \
  curl \
  git \
  make \
  openssl \
  unzip
```

Installing Docker on your system:

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

### Step 2: Get the Intel® SceneScape source code

**Note:** These operations must be executed when logged in as a standard (non-root) user. **Do NOT use root or sudo.**

1. Clone the SceneScape repository:

```bash
git clone https://github.com/open-edge-platform/scenescape.git
```

2. Change directories to the cloned repository:

```bash
cd scenescape/
```

**Note**: The default branch is `main`. To work with a stable release version, list the available tags and checkout specific version tag:

```bash
git tag
git checkout <tag-version>
```

Alternatively, download and extract the sources of a stable release:

1.  Download the Intel® SceneScape software archive from https://github.com/open-edge-platform/scenescape/releases.

2.  Extract the Intel® SceneScape archive on the target Ubuntu 22.04 system. Change directories to the extracted Intel® SceneScape folder.
    ```bash
    cd scenescape-<version>/
    ```
3.  Follow instructions in `Getting-Started-Guide` specific to that release version.

### Step 3: Build Intel® SceneScape container images

Build container images:

```bash
make
```

The build may take around 15 minutes depending on target machine.
This step generates common base docker image and docker images for all microservices.

By default, a parallel build is being run with the number of jobs equal to the number of processors in the system.
Optionally, the number of jobs can be adjusted by setting the `JOBS` variable, e.g. to achieve sequential building:

```bash
make JOBS=1
```

### Step 4 (Optional): Build dependency list of Intel® SceneScape container images

```bash
make list-dependencies
```

This step generates dependency lists. Two separate files are created for system packages and Python packages per each microservice image.

### Step 5: Deploy Intel® SceneScape demo to the target system

Before deploying the demo of Intel® SceneScape for the first time, please set the environment variable SUPASS with the super user password for logging into Intel® SceneScape.
Important: This should be different than the password for your system user.

```bash
export SUPASS=<password>
```

```bash
make demo
```

### Step 6: Verify a successful deployment

If you are running remotely, connect using `"https://<ip_address>"` or `"https://<hostname>"`, using the correct IP address or hostname of the remote Intel® SceneScape system. If accessing on a local system use `"https://localhost"`. If you see a certificate warning, click the prompts to continue to the site. For example, in Chrome click "Advanced" and then "Proceed to &lt;ip_address> (unsafe)".

> **Note:** These certificate warnings are expected due to the use of a self-signed certificate for initial deployment purposes. This certificate is generated at deploy time and is unique to the instance.

### Logging In

Enter "admin" for the user name and the value you typed earlier for SUPASS.

### Stopping the System

To stop the containers, use the following command in the project directory:

```console
$ docker compose down --remove-orphans
```

### Starting the System

To start after the first time, use the following command in the project directory:

```console
$ docker compose up -d
```

## Summary

Intel® SceneScape was downloaded, built and deployed onto a fresh Ubuntu 22.04 system. Using the web user interface, Intel® SceneScape provides two scenes by default that can be explored running from stored video data.
![SceneScape WebUI Homepage](images/homepage.png)

- **Note** the “Documentation” menu option, click to view the Intel® SceneScape HTML version of the documentation in the browser.

## Next Steps

- **How to enable reidentification**
  - [How to enable reidentification](How-to-enable-reidentification.md): Step-by-step guide to enable reidentification.

- **How to use sensor types**
  - [How to use Sensor types](How-to-use-sensor-types.md): Step-by-step guide to getting started with sensor types.

- **How to use 3D UI**
  - [How to use 3D UI](How-to-use-3D-UI.md): A guide on how use 3D UI

- **How to create a Geti trained AI models and integrate it with Intel® SceneScape.**
  - [Geti AI model integration](How-to-integrate-geti-trained-model.md): Step-by-step guide for integrating a Geti trained AI model with Intel® SceneScape.

- **How to visualize regions**
  - [How to visualize regions](How-to-visualize-regions.md): Step-by-step guide to getting started with visualizing regions.

- **How to configure a hierarchy of scenes**
  - [How to configure a hierarchy of scenes](How-to-configure-a-hierarchy-of-scenes.md): Step-by-step guide to configuring a hierarchy of scenes.

- **How to manually calibrate cameras**
  - [How to manually calibrate cameras](How-to-manually-calibrate-cameras.md): Step-by-step guide to performing Manual Camera Calibration.

- **How to autocalibrate cameras using visual features**
  - [How to autocalibrate cameras using visual features](How-to-autocalibrate-cameras-using-visual-features.md): Step-by-step guide to performing Auto Camera Calibration using Visual Features.

- **How to autocalibrate cameras using Apriltags**
  - [How to autocalibrate cameras using Apriltags](How-to-autocalibrate-cameras-using-apriltags.md): Step-by-step guide to performing Auto Camera Calibration using Apriltags.

- **How to upgrade Intel® SceneScape**
  - [How to upgrade Intel Scenescape](How-to-upgrade.md): Step-by-step guide for upgrading from an older version of Intel® SceneScape.

- **How to inference using Nvidia GPU with OVMS**
  - [How to inference using Nvidia GPU with OVMS](How-to-inference-using-Nvidia-gpu-with-OVMS.md): Step-by-step guide for enabling inference on Nvidia GPU using OVMS.

- **How to configure geospatial coordinates**
  - [How to Configure Geospatial Coordinates for a Scene](How-to-configure-geospatial-coordinates.md): Step-by-step guide for configuring geographic coordinates output in object detections.

- **How to configure spatial analytics**
  - [How to Configure Spatial Analytics](How-to-configure-spatial-analytics.md): Step-by-step guide to set up and use Regions of Interest (ROIs) and Tripwires.

- **How to define object properties**
  - [How to Define Object Properties](How-to-define-object-properties.md): Step-by-step guide for configuring the properties of an object class.

## Learn More

- Understand the components, services, architecture, and data flow, in
  the [Overview](Overview.md).
- Follow examples to become familiar with the core functionality of Intel® SceneScape, in
  [Tutorial](Tutorial.md).
- Optimizing security posture for a Intel® SceneScape installation [Hardening Guide for Custom TLS](hardening-guide.md)
