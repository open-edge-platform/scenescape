# SceneScape User / Developer Training for 2026.0 Open-Edge-Platform release

## Switch from Percebro to DLS-PS. State of Dynamic Camera Configuration

- Switch from Percebro to DLSPS as visual analytics engine (`v1.4.0`)
  - Rationale
    - Increase component reuse in the organization and reduce duplicated efforts
    - Engineering resource usage optimization (maintain single visual analytics solution)
- DLStreamer-Pipeline-Server
  - Overview DLSPS vs DLS vs GStreamer
  - DLStreamer capabilities
  - Docker configuration example (`dlstreamer-pipeline-server/queuing-config*.json`)
- Dynamic Camera Configuration in K8S **(video recorded)**
  - Feature overview (`docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md`)
  - User interface overview
  - Helm Chart configuration
  - Live demo
  - (optional) Advanced topics
    - Adding custom models
    - Pipeline runner as a offline tool for custom pipeline generation (`tools/pipeline_runner`)
  - Feature parity vs Percebro

## Controller performance optimizations

- ADR: docs/adr/0003-scaling-controller-performance.md
  - Problem definition
  - Short- and long-term solutions
- **(video recorded)**
  - Time-chunking feature overview
  - Tracker configuration overview
  - Controller observability
  - Live demo with 100 objects

## Volume mounts **(video recorded)**

- Volume vs bind mount in Docker - overview
- Volume mounts used in SceneScape Docker deployment
- How to access and use SceneScape volume mounts (`docs/user-guide/other-topics/how-to-manage-files-in-volumes.md`)
