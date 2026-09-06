# Installation

- **Time to Complete:** 30-45 minutes

## Prerequisites

- Verify you meet the [System Requirements](./system-requirements.md).

- Install required software such as Docker; see [System Requirements](./system-requirements.md) for details.

## Step 1: Get Scenescape

<!--hide_directive::::{tab-set}hide_directive-->
<!--hide_directive:::{tab-item}hide_directive--> **Download a release**

Note that these operations must be executed when logged in as a standard (non-root) user. **Do NOT use root or sudo.**

1. Download the Scenescape software archive from <https://github.com/open-edge-platform/scenescape/releases>.

2. Extract the Scenescape archive on the target Ubuntu system. Change directories to the extracted Scenescape folder.

   ```bash
   cd scenescape-<version>
   ```

<!--hide_directive:::hide_directive-->
<!--hide_directive:::{tab-item}hide_directive--> **Get the source code**

Clone the repository and change directories to the cloned repository:

```bash
git clone https://github.com/open-edge-platform/scenescape.git -b main
cd scenescape/
```

**Note**: The default branch is `main`. To work with a stable release version, list the available tags and checkout a specific version tag:

```bash
git tag
git checkout <tag-version>
```

<!--hide_directive:::hide_directive-->
<!--hide_directive::::hide_directive-->

## Step 2: Build Scenescape container images

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

### (Optional): Build dependency list of Scenescape container images

```bash
make list-dependencies
```

This step generates dependency lists. Two separate files are created for system packages and Python packages per each microservice image.

## Step 3: Deploy Scenescape demo to the target system

Before deploying the demo of Scenescape for the first time, please set the environment variable SUPASS with the super user password for logging into Scenescape.
Important: This should be different than the password for your system user.

```bash
export SUPASS=<password>
```

```bash
make demo
```

The Docker Compose demo targets are tiered, each building on the previous one:

| Target      | Includes                                                |
| ----------- | ------------------------------------------------------- |
| `demo`      | Core services with tracking, without ReID               |
| `demo-reid` | `demo` plus the ReID vector database                    |
| `demo-all`  | `demo-reid` plus cluster analytics and mapping services |

The ReID targets use VDMS by default. Set `REID_BACKEND=qdrant` to use Qdrant:

```bash
make demo-reid
make demo-reid REID_BACKEND=qdrant
```

`make demo-close` remembers the selected override and stops the matching
deployment.

## Step 4: Verify a successful deployment

If you are running remotely, connect using `https://<ip_address>` or `https://<hostname>`, using the correct IP address or hostname of the remote Scenescape system. If accessing on a local system use `https://localhost`. If you see a certificate warning, click the prompts to continue to the site. For example, in Chrome click "Advanced" and then "Proceed to &lt;ip_address> (unsafe)".

> **Note:** These certificate warnings are expected due to the use of a self-signed certificate for initial deployment purposes. This certificate is generated at deploy time and is unique to the instance.

### Logging In

Enter "admin" for the user name and the value you typed earlier for SUPASS.

### Docker Compose Profiles

Scenescape uses [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/) to organize services into logical groups. When starting or stopping services, you must specify the same profile(s) used during deployment.

The following profiles are available:

| Profile             | Description                                                                             |
| ------------------- | --------------------------------------------------------------------------------------- |
| `controller`        | Scene Controller (tracking) + Analytics service. Used by `make demo`.                   |
| `mapping`           | Enables mapping service.                                                                |
| `cluster-analytics` | Enables cluster-analytics service.                                                      |
| `tracker`           | Tracker service + Analytics service (no Scene Controller). Used by `make demo-tracker`. |

> **ReID backends:** The `demo-reid` and `demo-all` targets default to VDMS (`REID_BACKEND=vdms`); set `REID_BACKEND=qdrant` to switch. For raw Compose, add exactly one of `sample_data/docker-compose.vdms-override.yml` or `sample_data/docker-compose.qdrant-override.yml`. Both overrides provide the same logical `reid` service, shared host `reid.scenescape.intel.com`, port `55555`, TLS settings, and certificates. See [Selecting the ReID Vector Database Backend](../other-topics/how-to-enable-reidentification.md#selecting-the-reid-vector-database-backend).

Profiles can be specified on the command line with `--profile`:

```console
docker compose --profile controller up -d
```

Multiple profiles can be combined:

```console
docker compose --profile controller --profile mapping up -d
```

Alternatively, profiles can be set via the `COMPOSE_PROFILES` environment variable:

```console
export COMPOSE_PROFILES=controller
docker compose up -d
```

For multiple profiles, use a comma-separated list:

```console
export COMPOSE_PROFILES=controller,mapping
docker compose up -d
```

For more details, see the [Docker Compose profiles documentation](https://docs.docker.com/compose/how-tos/profiles/) and the [COMPOSE_PROFILES environment variable reference](https://docs.docker.com/compose/how-tos/environment-variables/envvars/#compose_profiles).

> **Note:** The `--profile` flags used with `docker compose down` must match those used when starting the services. Otherwise, containers started under a specific profile will remain running.

### Stopping the System

To stop the containers, use the following command in the project directory (see [Docker Compose Profiles](#docker-compose-profiles) for details on choosing profiles):

```console
docker compose --profile controller down --remove-orphans
```

### Starting the System

To start after the first time, use the following command in the project directory:

```console
docker compose --profile controller up -d
```

## Summary

Scenescape was downloaded, built and deployed onto a fresh Ubuntu system. Using the web user interface, Scenescape provides two scenes by default that can be explored running from stored video data.

![Scenescape WebUI Homepage](../_assets/ui/homepage.png "scenescape web ui homepage")

> **Note:** The "Documentation" menu option allows you to view Scenescape HTML version of the documentation in the browser.

## Next Steps

- Check [Deploy Scenescape](../how-to-guides/deploy-scenescape-using-prebuilt-containers.md) for step-by-step instructions on how to deploy Scenescape using prebuilt Docker images.

### Explore other topics

- [How to Define Object Properties](../other-topics/how-to-define-object-properties.md): Step-by-step guide for configuring the properties of an object class.

- [How to enable reidentification](../other-topics/how-to-enable-reidentification.md): Step-by-step guide to enable reidentification.

- [Viewing Re-identification Metrics](../other-topics/how-to-view-reid-metrics.md): Guide for exposing and querying ReID match-latency, camera-count, and tracked-object-count metrics via OpenTelemetry.

- [How to Enable Observability (Experimental)](../other-topics/how-to-enable-observability.md): Guide for enabling OpenTelemetry-based metrics and distributed traces for the Scene Controller and Tracker Service.

- [Geti AI model integration](../other-topics/how-to-integrate-geti-trained-model.md): Step-by-step guide for integrating a Geti trained AI model with Scenescape.

- [Running License Plate Recognition with 3D Object Detection](../other-topics/how-to-run-LPR-with-3D-object-detection.md): Step-by-step guide for running license plate recognition with 3D object detection.

- [How to Configure DL Streamer Video Pipeline](../other-topics/how-to-configure-dlstreamer-video-pipeline.md): Step-by-step guide for configuring DL Streamer video pipeline.

- [Model configuration file format](../other-topics/model-configuration-file-format.md): Model configuration file overview.

- [How to Manage Files in Volumes](../other-topics/how-to-manage-files-in-volumes.md): Step-by-step guide for managing files in Docker and Kubernetes volumes.

## Additional Resources

- [How to upgrade Scenescape](../additional-resources/how-to-upgrade.md): Step-by-step guide for upgrading from an older version of Scenescape.

- [How Scenescape converts Pixel-Based Bounding Boxes to Normalized Image Space](../additional-resources/convert-object-detections-to-normalized-image-space.md)

- [Hardening Guide for Custom TLS](../additional-resources/hardening-guide.md): Optimizing security posture for a Scenescape installation.

- [Release Notes](../release-notes.md)
