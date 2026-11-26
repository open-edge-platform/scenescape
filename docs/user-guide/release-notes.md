# Release Notes: Scenescape

## Version 2026.3.0

**Release Date:** December 7, 2026

**Upgrade Notes:**

- **2D map origin for GLB scenes:** The 2D view now places objects using the world position of the map image's bottom-left corner. Previously, it assumed this corner was at world `(0, 0)`, so objects were drawn offset from the floor plan for most GLB scene maps. During the database upgrade, existing GLB scenes have their 2D thumbnail, scale, and origin regenerated. Regions, tripwires, and singleton sensor areas that were drawn in the 2D view before the upgrade will appear shifted on the 2D map. Their stored world coordinates are unchanged, and the new position is where they actually are in the world. Re-check them and redraw any that you placed by eye against the old map. The upgrade logs a warning for each affected scene. See [How to Upgrade](./additional-resources/how-to-upgrade.md#re-check-2d-regions-tripwires-and-sensor-areas-on-glb-scenes).
- **Pre-populated scenes are required to be uploaded in run-time with a dedicated tool**: Added support for fresh Scenescape deployment. Removed support for loading prepopulated scenes on startup. Introduced Scene Upload Tool embedded into Manager container. To upgrade add a scene upload step on your application's startup. See [link to the documentation TBD]

**New:**

- **PTZ camera support:** New Positioning service, available on Docker Hub at [intel/scenescape-positioning](https://hub.docker.com/r/intel/scenescape-positioning) [link to the feature documentation TBD]:
  - Polls ONVIF PTZ cameras and publishes a resolved scene pose from a calibrated pan/tilt model
  - Scene Controller can project detections with that pose.
  - Import the measured `ptz_calibration` block through the Manager API. The Tracker does not consume PTZ poses in this release
- **Moving cameras and platforms:**
  - External sources can publish pixel detections. The Scene Controller projects them with the source pose and camera intrinsics
  - A moving platform can report observations from several mounted cameras
  - The 3D view draws platform camera frustums
  - Added a simulated drone-camera demo that publishes a moving view through the external-source contract [link to the README TBD]
- **Handheld scenes:** Pair a scene from a handheld app with a scene QR code, upload a map from the device, and follow a moving camera's pose, optics, and measured depth. Operators can preview, activate, or delete source maps per mapping method
- **Automated ROI creation:** On a geospatial scene, propose regions from OpenStreetMap roads and footways, limit the query to a selected area, edit or merge the proposals, and save the ones you keep [link to the documentation TBD]
- **Multi-modal fusion along with 3D camera and sensor projection controls:**
  - Turn projections on or off for every camera and LiDAR/radar sensor, and set a shared projection opacity
  - Show a live sensor point cloud, with point size and opacity, when the publisher answers `getpointcloud`
  - Support fusion of 3D detections with yaw and Z measured in the tracker [link to the ADR documentation TBD]
  - Added a perceptual-sensor CLI tool for the Auto Calibration localization API
- **Probabilistic tracking and Spatial Performance Primitives (SPP) integration in Tracker and Controller:** [link to the ADR and design documentation TBD]
  - Experimental Observation Processor service [link to the ADR and design documentation TBD] (Docker Compose profile only) turns 2D detections into world-space measurements and can condition them on the scene mesh. In that mode, published tracks include location uncertainty. It integrates standalone SPP libraries: Frustum Gaussian and Observation Conditioner.
  - Improvements in Unscented Kalman Filter (UKF) and Interactive Mixing Model (IMM) in robot-vision library including enhanced, velocity-dependent per-model process noise
  - Optional covariance-aware Mahalanobis association in robot-vision library. The configs shipped with the release keep the legacy Euclidean association method.
  - Tracking of height and vertical velocity for non-planar motion
  - Integrated probability-aware tracking in Tracker and Controller enabled with an experimental flag including: geometry-derived measurement noise derived from gRPC call to Observation Processor, uncertainty-weighted multi-camera fusion, IMM/UKF covariance handling and tracked object state uncertainty in the MQTT output
  - SPP demo and new evaluation dataset for non-planar tracking on Rolling Terrain scene [documentation link TBD]
- **ReID service:** Extracted the ReID database contract into a standalone service, available on Docker Hub at [intel/scenescape-reid](https://hub.docker.com/r/intel/scenescape-reid) [link to the documentation TBD]:
  - gRPC API for match, gallery maintenance, and authorized person-of-interest enrollment
  - The Tracker can publish embeddings to the service and consume ReID decisions
  - The Scene Controller still uses its in-process ReID path
- **Track GID labels on camera images:** The video pipeline can draw scene track GIDs on the annotated JPEG used by live view. Off by default
- **Sample application:** Added a Node-RED sample (`make sample-app-up`) that subscribes to scene counts, ROI occupancy, and tripwire crossings, plus a guide for building an application on Scenescape MQTT and REST [link to the documentation TBD]
- **Experimental MLOps flow:** Superusers can store GStreamer pipelines, import them from ViPPET, and run a selected pipeline on DL Streamer Pipeline Server 2.0. Off by default, enabled with an experimental flag in Manager and supported on Docker Compose only [link to the documentation TBD]

**Improved:**

- Default person-detection pipelines and the downloaded model set now use YOLOX-S
- Scene upload through the REST API, with the scene uploader CLI included in the Manager image and configurable import and scene-processing timeouts
- Faster import of GLB scene maps
- The Scene Controller follows pagination when it reads REST configuration, so large scenes are loaded in full
- AprilTag registration runs again when a scene map is replaced
- Tracker evaluation ground truth uses timestamps instead of frame numbers. Added an offline ReID model evaluator and crop review workflow
- Lower jitter for the Controller-Immediate tracker configuration, and rotation hysteresis on tracked heading
- Tracker service feature parity with Controller:
  - the C++ Tracker accepts 3D detections (`translation`, `size`, and optional `rotation`) in addition to pixel boxes, and projects TYPE_2 object classes the same way as the Scene Controller
  - [more items TBD]
- Testing and documentation:
  - Automated 3D UI coverage for regions, tripwires, camera deletion, and camera position
  - Pre-merge test coverage check
  - Deployment documentation split into preparation, Docker, Kubernetes, and demo guides

**Fixed:**

- MQTT skipped messages while live view was turned on
- Invalidating one scene rebuilt every live scene. A failing hierarchy message rebuilt the scene on every message. Scene-cache rebuilds leaked tracker threads, timers, and ReID clients
- Remote child MQTT clients reconnected in a loop and leaked Scene Controller threads. Child-scene overlays stayed stale after changes
- Scene import dropped calibration for orphaned cameras and dropped remote hierarchy links
- Polycam zip import for markerless calibration
- Manual calibration could stay on an outlier pose. AprilTag calibration could save an unstable pose, and the preview projection could disagree with the saved pose
- Camera pose was not reset when the camera was assigned to a different scene
- Autocalibration failed in Kubernetes. The calibration page did not refresh when registration finished. Mapping could place unrelated cameras too close together, and a map from the Mapping service was not applied to demo scenes
- V4L2 camera pipelines failed to link on Kubernetes. Classification-model metadata was missing in Kubernetes deployments
- Geospatial output kept publishing LLA fields after the scene transform had failed
- GLB thumbnails did not render in a headless Manager
- The web UI could fail silently when a JavaScript asset did not load
- Login kept leading and trailing spaces in the username

## Version 2026.2.0

**Release Date:** September 9, 2026

**New:**

- **Analytics Service:** Extracted analytics functionality from the Scene Controller into a new, separate service, available on Docker Hub at [intel/scenescape-analytics](https://hub.docker.com/r/intel/scenescape-analytics):
  - Computes region, tripwire, sensor, volumetric analytics, and camera bounds for tracked objects
  - Regulates output to a configurable max rate
- **Mapping Service:** No longer an experimental feature; now officially released with images available on Docker Hub at [intel/scenescape-mapping](https://hub.docker.com/r/intel/scenescape-mapping).
- **Cluster Analytics Service:** No longer an experimental feature; now officially released with images available on Docker Hub at [intel/scenescape-cluster-analytics](https://hub.docker.com/r/intel/scenescape-cluster-analytics).
- ReID improvements:
  - Added visual indicator to track objects in 3D UI
  - Exposed ReID Match Latency Metrics
  - Added shared ReID instance support across multiple scenes, including child and parent scenes
  - Added Qdrant vector database as a ReID backend
  - Added persistent attribute restoration on ReID match
  - Added server-side eviction of expired VDMS descriptors preventing unbounded storage growth
- LiDAR Support:
  - Added point-cloud based localization in Auto Calibration Service
  - Added example deployment showcasing usage of LiDARs + Cameras with Intel® Scenescape
- Model Download service integration: Switched from Intel® Scenescape-specific model installer to [Intel Model Download Microservice](https://hub.docker.com/r/intel/model-download)
- Analytics pipeline improvements: Migrated old gvapython-based scripts to custom GStreamer Elements
- Added support for multi-camera object metadata fusion in time-chunking
- Added support for publishing external observations over MQTT, designed for supporting moving sensors, autonomous physical agents and ephemeral child scenes via a unified approach
- Tracker Evaluation Pipeline:
  - Added runtime observability to the Tracker evaluation black-box harness and added time-chunking performance counters
  - Stabilized evaluation results
  - Adopted Wildtrack dataset for evaluation
- Added a new user-facing agent skill that deploys Intel® Scenescape. It gathers required user inputs and sets up the video analytics pipeline, scene creation, camera configuration, scene reconstruction (if required), tracker and ReID configuration, and verification workflow. It can also create downstream business logic that leverages the spatial analytics outputs

**Improved:**

- Testing & Quality:
  - Expanded automation coverage:
    - 3D asset CRUD & camera creation UI workflows
    - Cluster-analytics unit and component test suites
    - Autocalibration
  - Mock tracker for unit tests; removed unnecessary build dependencies
  - Improved test stability and infrastructure:
    - Automatic cleanup of residual test resources after aborted runs
    - Increased reliability of k8s and helm chart tests
    - Test logger adjustments for clearer diagnostics

**Fixed:**

- Multi-controller VDMS schema verification
- Hardened authorization on some API endpoints
- ROI names displayed when "Visualize ROIs" is disabled
- Objects not tracked in analytics-only mode after scene import
- Registration error status handling in Autocalibration
- Polycam data overwrite issue
- Pose estimation accuracy degradation during longer occlusions
- Kubernetes:
  - Parent-child scene relation issues
  - Importing scene API returning null for all attributes

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- Tracking & Analytics
  - Added Tracker Evaluation Pipeline enhancements:
    - Multi-evaluator support
    - New jitter metrics (RMS jerk, acceleration variance)
    - Per-frame diagnostic evaluator
  - High-performance tracker improvements:
    - Supports visibility, confidence, and detection metadata
    - Includes NTP-based time correction

- Controller uses pose estimation metadata to mitigate partial occlusion of a person. Implementation is extensible to other object types.

- Re-ID feature now works with embedding vectors of arbitrary size, provides cosine distance as a similarity metric and publishes track state for determining re-id accuracy.

**Improved:**

- Testing & Quality
  - Major API test rework and reporting improvements
  - Expanded automation coverage:
    - Mapping, autocalibration, MQTT events, retrack, linked scenes
  - Added UI tests
  - Migration of legacy tests to scenario-based JSON
  - Improved test stability and fixtures
  - Added weekly test coverage for releases

- Documentation:
  - Major documentation restructuring and alignment
  - Improved navigation, references, and formatting
  - Standardized message format documentation

**Fixed:**

- Metadata passthrough issues in controller
- Database migration flow issues
- Corrected camera pose and scale for VGGT models
- Sensor color update inconsistencies
- REID schema initialization failures
- API behavior, input validation
- Missing TRS matrix fields
- Calibration API handling of invalid images
- Asset update failures for invalid IDs
- Docker cache handling, Docker image size regressions
- Resolved bind mount permission errors
- NTP pod CrashLoopBackOff issue

## Version 2026.0.0

**Release Date:** April 6, 2026

**Major Features and Enhancements:**

- Standalone tracking microservice that can vertically scale to track 1000 objects.
- Time-Chunked Tracking: Advanced time-chunking algorithms for improved tracking performance and accuracy
- Extended Re-identification with a 2-tier architecture to improve Re-ID quality and scalability.
- Mapping service enhancements: Video-Based Mapping, CLAHE pre-processing to improve mesh appearance
- Controller outputs augmented to work with a physics engine
- Controller Analytics Mode: New analytics-only mode for the controller with schema validation (retired; use the Analytics microservice)

**Improved:**

- Debian Migration: Complete migration from Ubuntu to Debian base images across all services for reduced size and improved security
- Non-Root Users: All services now run as non-root users with custom scenescape user implementation
- Gateway API Resources: Migration from Ingress to Gateway API for improved networking
- USB Camera Support: Dynamic camera configuration with USB camera support in Kubernetes
- Test Automation: Comprehensive API test automation for all major endpoints (cameras, sensors, assets, regions, tripwires, users)
- Performance Testing: Tracker evaluation pipeline with MVP implementation

**Performance and Optimization:**

- Memory Leak Fixes: Resolved memory usage issues that caused steady increases over time
- Thread Safety: Improved thread safety in Tracker Service MQTT client during shutdown
- Resource Cleanup: Enhanced cleanup processes for tests and deployments
- Build Optimization: Improved build paths, dependency management, and Docker caching
- Image Size Optimization: Significant reduction in container image sizes through dependency optimization

**Video Analytics Updates:**

- Pipeline Optimization: Improved pipeline generation and GPU utilization
- Model Management: Enhanced model downloading and management with updated model sets

**Developer Experience:**

- Copilot Integration: Added copilot instructions for enhanced developer experience
- Deployment Scripts: Enhanced deployment scripts with port installation choices

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

:::
hide_directive-->
