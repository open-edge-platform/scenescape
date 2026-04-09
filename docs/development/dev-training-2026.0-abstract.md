<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# SceneScape User / Developer Training — 2026.0 Release Abstract

This document is the training abstract for the Intel® SceneScape 2026.0 Open-Edge-Platform release. The training is delivered as a live session for engineers and experienced users familiar with SceneScape `v1.3.0` and earlier. Selected sections are also recorded and made available as standalone video materials — these are marked with **(video recorded)** below.

The training covers three topics: the migration from Percebro to DLStreamer-Pipeline-Server, controller performance optimizations, and Docker volume management.

---

## 1. Switch from Percebro to DLS-PS. State of Dynamic Camera Configuration

### 1.1 Switch from Percebro to DLSPS as Visual Analytics Engine (`v1.4.0`)

Starting with `v1.4.0`, SceneScape replaced the internally developed Percebro visual analytics engine with Intel DLStreamer-Pipeline-Server (DLS-PS). Percebro was an OpenVINO-based solution maintained in-house and last shipped in the `v1.3.0` release. The switch was driven by the goal to consolidate on a single visual analytics stack across the organization, reducing duplicated engineering effort and increasing component reuse.

#### Rationale

- **Component reuse**: DLStreamer is a shared Intel asset. Adopting it eliminates the need to maintain a separate, internally developed inference runtime and allows all teams to benefit from a single, actively developed codebase.
- **Engineering resource optimization**: Maintaining Percebro alongside DLStreamer required parallel effort for model integration, hardware enablement, and bug fixes. Consolidating onto DLS-PS frees engineering capacity for higher-value work on SceneScape-specific features.

### 1.2 DLStreamer-Pipeline-Server

#### Overview: DLSPS vs DLS vs GStreamer

DLStreamer-Pipeline-Server (DLS-PS) is a REST-driven microservice built on top of Intel® DLStreamer (DLS), which itself is a set of GStreamer Video Analytics (GVA) plugins. The layering is: GStreamer provides the media pipeline framework, DLStreamer adds AI inference elements (`gvadetect`, `gvaclassify`, `gvametaconvert`, etc.), and DLS-PS wraps these into a configurable, container-ready server with REST interface and JSON static configuration file. Supported input sources include RTSP streams, MJPEG, local video files, and V4L2 devices.

#### DLStreamer Capabilities

DLStreamer supports flexible model chaining — multiple inference stages can be composed sequentially or in parallel within a single pipeline. Each stage can target a different hardware device (CPU, GPU, or NPU), enabling fine-grained performance tuning.

#### Docker Configuration Example

Pre-built pipeline configurations are shipped in the [`dlstreamer-pipeline-server/`](../../dlstreamer-pipeline-server/) directory. Files like `queuing-config.json`, `queuing-config-gpu.json`, and `queuing-config-npu.json` define ready-to-use pipelines for different hardware targets. Each configuration specifies the GStreamer pipeline string, model paths, inference device, and post-processing scripts. These files serve as both deployment artifacts and templates for creating custom configurations.

### 1.3 Dynamic Camera Configuration in K8S **(video recorded)**

#### Feature Overview

In SceneScape Kubernetes deployments, cameras can be added, modified, and removed at runtime through the SceneScape web UI — no redeployment or Helm upgrade is required. When a user configures a camera, the system auto-generates a complete GStreamer pipeline string from the provided settings (video source, model chain, decode device, detection labels). The Manager's `kubeclient` component then creates a dedicated K8S Deployment and ConfigMap for each camera. For details, see the [DLStreamer video pipeline configuration guide](../user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md).

#### User Interface Overview

The camera calibration page exposes fields for the video source URI, camera chain (model selection with device assignment), decode device, detection label filters, and camera intrinsics/distortion parameters. Users can preview the auto-generated GStreamer pipeline or supply a fully custom pipeline string for advanced use cases. Models are referenced using short names (e.g., `retail`, `pvbcross16`, `reid`, `agegender`, `vehattr`) and can be combined into chains such as `retail=GPU+reid=GPU` (person detection followed by re-identification, both on GPU) or `pvbcross16+[vehattr,reid]` (multi-class detection with parallel attribute classification and re-identification).

#### Helm Chart Configuration

The SceneScape Helm chart ([`kubernetes/scenescape-chart/`](../../kubernetes/scenescape-chart/)) includes values for the DLS-PS container image, tag, and pull policy under the `kubeclient.vaPipeline`, `retail`, and `queuing` sections. Storage class, resource limits, and RTSP streaming options are also configurable per scene type. Video streaming deployments (retail and queuing video streaming to mediaserver, which exposes them as synchronized RTSP streams) are defined as Helm templates, while dynamically created camera pipeline deployments (DLSPS) are managed by `kubeclient` at runtime.

#### Live Demo

A live demonstration walks through
- adding a camera via the web UI, observing the auto-generated K8S deployment, and verifying that detections flow through MQTT to the Scene Controller.
- usage of models chaining and GPU/NPU acceleration.
- editing pipeline string.
- (optionally) uploading a custom model to the model volume.

#### Advanced Topics (Optional)

- **Adding custom models**: Custom OpenVINO models can be placed in the models volume and referenced in the camera chain by adding a model configuration entry. The custom model needs to be added to `model-config.json` file, which enables pipeline generator to resolve the model path at pipeline build time.
- **Pipeline runner**: The [`tools/pipeline_runner`](../../tools/pipeline_runner/) is an offline command-line tool for generating and testing DLS-PS configurations outside a full SceneScape deployment. It accepts a camera settings JSON file, produces a complete DLS-PS config, and can run the pipeline locally with detection output captured to files.

#### Limitations and Feature Parity vs v1.3.0 (with Percebro)

The model chain syntax is aligned with Percebro's, including OpenVINO notation for inference device specification.

The following Pipeline Configurability features are not yet supported :
- Parallel model chaining.
- Camera frame rate and resolution control.
- Virtual cameras.
- Distortion correction.

Cross-stream batching is DLS-specific performance feature that is not yet supported in SceneScape dynamic camera configuration.

---

## 2. Controller Performance Optimizations

### 2.1 Architecture Decision Record

The performance requirements and design decisions are documented in [ADR-0003: Scaling Controller Performance](../adr/0003-scaling-controller-performance.md).

#### Problem Definition

The Scene Controller must support real-time tracking of 100 to 300 objects across multiple categories, with up to 4 cameras each streaming at 15 FPS. At these scales, the cumulative incoming frame rate can overwhelm the tracker, leading to dropped messages — particularly when multiple cameras and object categories are active simultaneously.

#### Short- and Long-Term Solutions

The **short-term solution** is time-chunking (see below), which addresses the multi-camera throughput bottleneck by buffering and batching detections. **Long-term approaches** on the roadmap include spatial indexing (processing only overlapping camera regions together) and a C++ rewrite of the tracking core to eliminate Python GIL limitations and enable true parallelism for high object counts.

### 2.2 Time-Chunking, Tracker Configuration, Observability, and Live Demo **(video recorded)**

#### Time-Chunking Feature Overview

Without time-chunking, the tracker processes each incoming camera frame individually at a rate equal to the cumulative FPS of all cameras. For example, 4 cameras at 15 FPS produce a cumulative 60 FPS that the tracker must sustain. When this cumulative rate exceeds the tracker's processing budget, incoming detections queue up and are eventually dropped — visible as `Tracker work queue is not empty` warnings in controller logs.

Time-chunking addresses this by decoupling the incoming detection rate from the tracker's processing rate. Instead of processing every frame as it arrives, the controller groups detections into fixed-length time windows of `1 / time_chunking_rate_fps` seconds and processes each group as a single batch. If a camera produces multiple frames within one window, only the most recent frame is kept — older frames are discarded. This bounds the tracker's workload to the configured `time_chunking_rate_fps` regardless of how many cameras are active.

The recommended starting point is `time_chunking_rate_fps = highest_camera_FPS` in the deployment, which avoids dropping any single-camera frames. The rate can be further decreased if additional throughput is needed, trading potential accuracy loss from dropped frames for lower tracker load. If high FPS from individual cameras is the primary source of pressure, it is recommended to first lower camera FPS to the minimum acceptable level before enabling time-chunking. For the full configuration guide, see [How to Configure the Tracker](../user-guide/microservices/controller/how-to-configure-tracker.md).

#### Tracker Configuration Overview

Tracker behavior is controlled through JSON configuration files in [`controller/config/`](../../controller/config/). The standard configuration is `tracker-config.json`; the time-chunking variant is `tracker-config-time-chunking.json`. Key parameters include:

- `time_chunking_enabled` — enables or disables the time-chunking mode.
- `time_chunking_rate_fps` — the fixed processing rate when time-chunking is active (recommended: match the highest camera FPS in the deployment).
- `max_unreliable_time_s` — delay before a newly tracked object is published (filters transient detections).
- `non_measurement_time_dynamic_s` / `non_measurement_time_static_s` — time before a moving or stationary track is deleted after losing detections.

All time-related parameters use seconds, ensuring consistent behavior regardless of individual camera frame rates.

#### Controller Observability

The controller exposes OpenTelemetry-based metrics and tracing, configured via environment variables. Metrics include MQTT message counters (`scenescape_controller_mqtt_messages`, `scenescape_controller_mqtt_messages_dropped`), handler and tracking duration histograms (`scenescape_controller_mqtt_handler_duration`, `scenescape_controller_tracking_duration`), and per-message object count histograms. Tracing supports configurable sampling ratios for production use. These signals provide visibility into message throughput, dropped frames, and processing latency — enabling operators to diagnose bottlenecks and tune tracker parameters. For the full list of CLI flags and environment variables, see the [Controller documentation](../user-guide/microservices/controller/controller.md).

#### Live Demo with 100 Objects

A live demonstration shows the controller processing synthetically generated 100 tracked objects from multiple cameras. The demo highlights tracker configuration update, metric dashboards showing dropped frames, message throughput and latency, and the effect of enabling time-chunking on system behavior.

---

## 3. Volume Mounts **(video recorded)**

### 3.1 Volume vs Bind Mount in Docker — Overview

Docker offers two primary storage mechanisms for containers: **named volumes** and **bind mounts**. Named volumes are managed entirely by Docker, persisted across container restarts, and are the preferred approach for data that must survive redeployment (databases, models, media). Bind mounts map a specific host directory into the container filesystem — they are useful for injecting configuration or secrets but are tied to the host's directory structure and are not portable.

### 3.2 Volume Mounts Used in SceneScape Docker Deployment

SceneScape defines several named volumes in [`docker-compose.yml`](../../docker-compose.yml):

| Volume | Purpose |
|---|---|
| `vol-db` | PostgreSQL database (scenes, cameras, configuration) |
| `vol-media` | Media files, scene assets, cached content |
| `vol-models` | OpenVINO Zoo AI models for inference |
| `vol-sample-data` | Sample videos and demo datasets |
| `vol-migrations` | Database schema migrations |
| `vol-netvlad_models` | NetVLAD model weights for autocalibration |
| `vol-datasets` | Calibration datasets |

Bind mounts are used for secrets (`${SECRETSDIR}` mounted read-only into services) and for DLS-PS user scripts (`dlstreamer-pipeline-server/user_scripts`). The `vol-db` volume is the most critical — it holds all persistent scene and camera configuration, and data loss is unrecoverable without a backup (`make backupdb`).

### 3.3 How to Access and Use SceneScape Volume Mounts

Users can inspect and manage volume contents using standard Docker CLI commands — for example, running a lightweight Alpine container with the target volume mounted to list, copy, or modify files. In Kubernetes deployments, `kubectl cp` and `kubectl exec` serve the same purpose. Common operations include populating the sample data volume (`make init-sample-data`), installing models (`make install-models`), and backing up the database volume (`make backupdb`). The full procedure is documented in [How to Manage Files in Volumes](../user-guide/other-topics/how-to-manage-files-in-volumes.md).

### 3.4 Live demo

A live demonstration shows how to list contents of `vol-models` volume and copy a new model to it.
