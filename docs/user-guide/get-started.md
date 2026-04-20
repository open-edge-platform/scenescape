# Get Started with Intel® SceneScape

- **Time to Complete:** 30-45 minutes

## Get Started

### Prerequisites

- Verify you meet the [System Requirements](./get-started/system-requirements.md).

- Install [Prerequisites](./get-started/prerequisites.md) such as Docker and other required software.

### Step 1: Get Intel® SceneScape

<!--hide_directive
::::{tab-set}
:::{tab-item} hide_directive--> **Download a release**

Note that these operations must be executed when logged in as a standard (non-root) user. **Do NOT use root or sudo.**

1. Download the Intel® SceneScape software archive from <https://github.com/open-edge-platform/scenescape/releases>.

2. Extract the Intel® SceneScape archive on the target Ubuntu system. Change directories to the extracted Intel® SceneScape folder.

   ```bash
   cd scenescape-<version>
   ```

<!--hide_directive
:::
:::{tab-item} hide_directive--> **Get the source code**

Clone the repository and change directories to the cloned repository:

```bash
git clone https://github.com/open-edge-platform/scenescape.git &&
cd scenescape/
```

**Note**: The default branch is `main`. To work with a stable release version, list the available tags and checkout a specific version tag:

```bash
git tag
git checkout <tag-version>
```

<!--hide_directive
:::
::::
hide_directive-->

### Step 2: Build Intel® SceneScape container images

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

#### (Optional): Build dependency list of Intel® SceneScape container images

```bash
make list-dependencies
```

This step generates dependency lists. Two separate files are created for system packages and Python packages per each microservice image.

### Step 3: Deploy Intel® SceneScape demo to the target system

Before deploying the demo of Intel® SceneScape for the first time, please set the environment variable SUPASS with the super user password for logging into Intel® SceneScape.
Important: This should be different than the password for your system user.

```bash
export SUPASS=<password>
```

```bash
make demo
```

### Step 4: Verify a successful deployment

If you are running remotely, connect using `https://<ip_address>` or `https://<hostname>`, using the correct IP address or hostname of the remote Intel® SceneScape system. If accessing on a local system use `https://localhost`. If you see a certificate warning, click the prompts to continue to the site. For example, in Chrome click "Advanced" and then "Proceed to &lt;ip_address> (unsafe)".

> **Note:** These certificate warnings are expected due to the use of a self-signed certificate for initial deployment purposes. This certificate is generated at deploy time and is unique to the instance.

#### Logging In

Enter "admin" for the user name and the value you typed earlier for SUPASS.

#### Docker Compose Profiles

Intel® SceneScape uses [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/) to organize services into logical groups. When starting or stopping services, you must specify the same profile(s) used during deployment.

The following profiles are available:

| Profile             | Description                                                                   |
| ------------------- | ----------------------------------------------------------------------------- |
| `controller`        | Scene Controller in default mode (analytics + tracking). Used by `make demo`. |
| `analytics`         | Scene Controller in analytics-only mode (without tracking).                   |
| `experimental`      | Enables mapping and cluster-analytics services.                               |
| `mapping`           | Enables mapping service only.                                                 |
| `cluster-analytics` | Enables cluster-analytics service only.                                       |
| `vdms`              | Enables the VDMS visual database service (used for re-identification).        |
| `tracker`           | Enables the tracker service.                                                  |

Profiles can be specified on the command line with `--profile`:

```console
docker compose --profile controller up -d
```

Multiple profiles can be combined:

```console
docker compose --profile controller --profile experimental up -d
```

Alternatively, profiles can be set via the `COMPOSE_PROFILES` environment variable:

```console
export COMPOSE_PROFILES=controller
docker compose up -d
```

For multiple profiles, use a comma-separated list:

```console
export COMPOSE_PROFILES=controller,experimental
docker compose up -d
```

For more details, see the [Docker Compose profiles documentation](https://docs.docker.com/compose/how-tos/profiles/) and the [COMPOSE_PROFILES environment variable reference](https://docs.docker.com/compose/how-tos/environment-variables/envvars/#compose_profiles).

> **Note:** The `--profile` flags used with `docker compose down` must match those used when starting the services. Otherwise, containers started under a specific profile will remain running.

#### Stopping the System

To stop the containers, use the following command in the project directory (see [Docker Compose Profiles](#docker-compose-profiles) for details on choosing profiles):

```console
docker compose --profile controller down --remove-orphans
```

#### Starting the System

To start after the first time, use the following command in the project directory:

```console
docker compose --profile controller up -d
```

## Summary

Intel® SceneScape was downloaded, built and deployed onto a fresh Ubuntu system. Using the web user interface, Intel® SceneScape provides two scenes by default that can be explored running from stored video data.

![SceneScape WebUI Homepage](./_assets/ui/homepage.png "scenescape web ui homepage")

> **Note:** The “Documentation” menu option allows you to view Intel® SceneScape HTML version of the documentation in the browser.

## Next Steps

- Check the [How-to Guides](./how-to-guides.md) for step-by-step instructions on how to perform specific tasks in Intel® SceneScape.

### Explore other topics

- [How to Define Object Properties](./other-topics/how-to-define-object-properties.md): Step-by-step guide for configuring the properties of an object class.

- [How to enable reidentification](./other-topics/how-to-enable-reidentification.md): Step-by-step guide to enable reidentification.

- [Geti AI model integration](./other-topics/how-to-integrate-geti-trained-model.md): Step-by-step guide for integrating a Geti trained AI model with Intel® SceneScape.

- [Running License Plate Recognition with 3D Object Detection](./other-topics/how-to-run-LPR-with-3D-object-detection.md): Step-by-step guide for running license plate recognition with 3D object detection.

- [How to Configure DL Streamer Video Pipeline](./other-topics/how-to-configure-dlstreamer-video-pipeline.md): Step-by-step guide for configuring DL Streamer video pipeline.

- [Model configuration file format](./other-topics/model-configuration-file-format.md): Model configuration file overview.

- [How to Manage Files in Volumes](./other-topics/how-to-manage-files-in-volumes.md): Step-by-step guide for managing files in Docker and Kubernetes volumes.

## Additional Resources

- [How to upgrade Intel® SceneScape](./additional-resources/how-to-upgrade.md): Step-by-step guide for upgrading from an older version of Intel® SceneScape.

- [How Intel® SceneScape converts Pixel-Based Bounding Boxes to Normalized Image Space](./additional-resources/convert-object-detections-to-normalized-image-space.md)

- [Hardening Guide for Custom TLS](./additional-resources/hardening-guide.md): Optimizing security posture for a Intel® SceneScape installation.

- [Release Notes](./release-notes.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/prerequisites.md

:::
hide_directive-->
