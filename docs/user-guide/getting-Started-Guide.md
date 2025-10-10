# Getting Started with Intel® SceneScape

- **Time to Complete:** 30-45 minutes

## Get Started

### Prerequisites

Check [System Requirements](system-requirements.md) before proceeding with rest of the steps in this documentation.

### Step 1: Install Prerequisites

The prerequisite software can be installed via the following commands on the Ubuntu host OS:

```console
sudo apt update
sudo apt install -y \
  curl \
  git \
  make \
  openssl \
  unzip
```

**Installing Docker on your system:**

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

### Step 2: Download and extract code of a Intel® SceneScape release

> **Note:** These operations must be executed when logged in as a standard (non-root) user. **Do NOT use root or sudo.**

1. Download the Intel® SceneScape software archive from <https://github.com/open-edge-platform/scenescape/releases>.

2. Extract the Intel® SceneScape archive on the target Ubuntu system. Change directories to the extracted Intel® SceneScape folder.

   ```bash
   cd scenescape-<version>/
   ```

3. When downloading older Scenescape releases, follow instructions in `Getting-Started-Guide` specific to that version.

#### Alternatively, get the Intel® SceneScape source code

1. Clone the SceneScape repository:

   ```bash
   git clone https://github.com/open-edge-platform/scenescape.git
   ```

2. Change directories to the cloned repository:

```bash
cd scenescape/
```

> **Note**: The default branch is `main`. To work with a stable release version, list the available tags and checkout specific version tag:

```bash
git tag
git checkout <tag-version>
```

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
docker compose down --remove-orphans
```

### Starting the System

To start after the first time, use the following command in the project directory:

```console
docker compose up -d
```

## Summary

Intel® SceneScape was downloaded, built and deployed onto a fresh Ubuntu system. Using the web user interface, Intel® SceneScape provides two scenes by default that can be explored running from stored video data.
![SceneScape WebUI Homepage](images/ui/homepage.png)

> **Note:** The “Documentation” menu option allows you to view Intel® SceneScape HTML version of the documentation in the browser.

## Next Steps

### Learn how to use Intel® SceneScape

- [Deployment Guide](./Using%20Intel%20SceneScape/How-to-deploy-scenescape-using-prebuilt-containers.md)

- [Tutorial](./Using%20Intel%20SceneScape/Tutorial.md): Follow examples to become familiar with the core functionality of Intel® SceneScape.

- [How to use 3D UI](./Using%20Intel%20SceneScape/How-to-use-3D-UI.md): Explore Intel® SceneScape powerful 3D UI

- [How to Integrate Cameras and Sensors into Intel® SceneScape](./Using%20Intel%20SceneScape/How-to-integrate-cameras-and-sensors.md): Step-by-step guide to basic data flow

- [Deploy SceneScape from Prebuilt containers](./Using%20Intel%20SceneScape/How-to-deploy-scenescape-using-prebuilt-containers.md): Step-by-step guide for deploying SceneScape using prebuilt containers.

### Build a Scene in Scenescape

- [How to Create and Configure a New Scene](./Building%20a%20Scene/How-to-create-new-scene.md): Step-by-step guide on how to create a live scene in Intel® SceneScape

- [How to use Sensor types](./Building%20a%20Scene/How-to-use-sensor-types.md): Step-by-step guide to getting started with sensor types.

- [How to visualize regions](./Building%20a%20Scene/How-to-visualize-regions.md): Step-by-step guide to getting started with visualizing regions.

- [How to configure a hierarchy of scenes](./Building%20a%20Scene/How-to-configure-a-hierarchy-of-scenes.md): Step-by-step guide to configuring a hierarchy of scenes.

- [How to Configure Geospatial Coordinates for a Scene](./Building%20a%20Scene/How-to-configure-geospatial-coordinates.md): Step-by-step guide for configuring geographic coordinates output in object detections.

- [How to Configure Spatial Analytics](./Building%20a%20Scene/How-to-configure-spatial-analytics.md): Step-by-step guide to set up and use Regions of Interest (ROIs) and Tripwires.

### Learn how to calibrate cameras for Intel® SceneScape

- [How to manually calibrate cameras](./Calibrating%20Cameras/How-to-manually-calibrate-cameras.md): Step-by-step guide to performing Manual Camera Calibration.

- [How to autocalibrate cameras using visual features](./Calibrating%20Cameras/How-to-autocalibrate-cameras-using-visual-features.md): Step-by-step guide to performing Auto Camera Calibration using Visual Features.

- [How to autocalibrate cameras using Apriltags](./Calibrating%20Cameras/How-to-autocalibrate-cameras-using-apriltags.md): Step-by-step guide to performing Auto Camera Calibration using Apriltags.

### Explore other topics

- [How to Define Object Properties](./Other%20Topics/How-to-define-object-properties.md): Step-by-step guide for configuring the properties of an object class.

- [How to enable reidentification](./Other%20Topics/How-to-enable-reidentification.md): Step-by-step guide to enable reidentification.

- [Geti AI model integration](./Other%20Topics/How-to-integrate-geti-trained-model.md): Step-by-step guide for integrating a Geti trained AI model with Intel® SceneScape.

- [Running License Plate Recognition with 3D Object Detection](./Other%20Topics/How-to-run-LPR-with-3D-object-detection.md): Step-by-step guide for running license plate recognition with 3D object detection.

- [How to Configure DLStreamer Video Pipeline](./Other%20Topics/How-to-configure-dlstreamer-video-pipeline.md): Step-by-step guide for configuring DLStreamer video pipeline.

- [Model configuration file format](./Other%20Topics/Model-configuration-file-format.md): Model configuration file overview.

## Additional Resources

- [How to upgrade Intel Scenescape](./Additional%20Resources/How-to-upgrade.md): Step-by-step guide for upgrading from an older version of Intel® SceneScape.

- [Hardening Guide for Custom TLS](./Additional%20Resources/hardening-guide.md): Optimizing security posture for a Intel® SceneScape installation

- [Release Notes](./Additional%20Resources/release-notes.md)

- [How Intel® SceneScape converts Pixel-Based Bounding Boxes to Normalized Image Space](./Additional%20Resources/convert-object-detections-to-normalized-image-space.md)
