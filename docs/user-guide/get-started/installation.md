# Installation

For a quick preview, follow the [Quick Start guide](./quickstart.md).

## Prerequisites

- Verify you meet the [System Requirements](./system-requirements.md).

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

## Step 2: Choose a Deployment

Scenescape can run on Docker Compose or on Kubernetes, and can be deployed clean (an empty scene database, ready for your own cameras and scenes) or with the bundled demo (two sample scenes preloaded with recorded video). Either way, you first need Scenescape's container images available, either built from source or as prebuilt images.

| I want to...                                    | Steps                                                                                                                                   |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Deploy clean Scenescape on Docker               | [Preparation](../how-to-guides/deployment/preparation.md) then [Deploy on Docker](../how-to-guides/deployment/deploy-docker.md)         |
| Deploy clean Scenescape on Kubernetes           | [Preparation](../how-to-guides/deployment/preparation.md) then [Deploy on Kubernetes](../how-to-guides/deployment/deploy-kubernetes.md) |
| Explore the bundled demo (Docker or Kubernetes) | [Preparation](../how-to-guides/deployment/preparation.md) then [Deploy the Demo](../how-to-guides/deployment/deploy-demo.md)            |

> **Note:** The Kubernetes guides assume a cluster already exists and `kubectl` is configured with access to it. To spin up a local, self-contained cluster for development or evaluation instead, see [Scenescape on Kubernetes](/kubernetes/README.md).

## Next Steps

- [Use Scenescape UI and Online Documentation](../how-to-guides/ui-tutorial.md): Navigate the web UI and view the online documentation, once you have deployed the demo.

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
