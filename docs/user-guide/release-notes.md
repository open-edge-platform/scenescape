# Release Notes: Scenescape

## Version 2026.2.0

**Release Date:** August 2026

**New:**

- **Analytics Service:** Extracted analytics functionality from the Scene Controller into a new, separate service.
  - Computes region, tripwire, sensor, volumetric analytics, and camera bounds for tracked objects
  - Regulates output to a configurable max rate

  Available on Docker Hub at [intel/scenescape-analytics](https://hub.docker.com/r/intel/scenescape-analytics)
- **Mapping Service:** No longer an experimental feature; now officially released with images available on Docker Hub at [intel/scenescape-mapping](https://hub.docker.com/r/intel/scenescape-mapping)
- **Cluster Analytics Service:** No longer an experimental feature; now officially released with images available on Docker Hub at [intel/scenescape-cluster-analytics](https://hub.docker.com/r/intel/scenescape-cluster-analytics)
- ReID improvements:
  - Added visual indicator to track objects in 3D UI
  - Exposed ReID Match Latency Metrics
  - Added shared ReID instance support across multiple scenes, including child and parent scenes
  - Added Qdrant vector database as a ReID backend
  - Added persistent attribute restoration on ReID match
  - Added support for publishing external observations over MQTT, designed for supporting moving sensors, autonomous physical agents and ephemeral child scenes via a unified approach
  - Added server-side eviction of expired VDMS descriptors preventing unbounded storage growth
- LiDAR Support:
  - Added point-cloud based localization in Auto Calibration Service
  - Added example deployment showcasing usage of LiDARs + Cameras with Intel® Scenescape
- Model Download service integration: Switched from Intel® Scenescape-specific model installer to [Intel Model Download Microservice](https://hub.docker.com/r/intel/model-download)
- Analytics pipeline improvements: Migrated old gvapython-based scripts to custom GStreamer Elements
- Added support for multi-camera object metadata fusion in time-chunking
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

**June 17, 2026**

**New**

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

**Improved**

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

**Fixed**

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

**April 6, 2026**

**Major Features and Enhancements**

- Standalone tracking microservice that can vertically scale to track 1000 objects.
- Time-Chunked Tracking: Advanced time-chunking algorithms for improved tracking performance and accuracy
- Extended Re-identification with a 2-tier architecture to improve Re-ID quality and scalability.
- Mapping service enhancements: Video-Based Mapping, CLAHE pre-processing to improve mesh appearance
- Controller outputs augmented to work with a physics engine
- Controller Analytics Mode: New analytics-only mode for the controller with schema validation (retired; use the Analytics microservice)

**Improved**

- Debian Migration: Complete migration from Ubuntu to Debian base images across all services for reduced size and improved security
- Non-Root Users: All services now run as non-root users with custom scenescape user implementation
- Gateway API Resources: Migration from Ingress to Gateway API for improved networking
- USB Camera Support: Dynamic camera configuration with USB camera support in Kubernetes
- Test Automation: Comprehensive API test automation for all major endpoints (cameras, sensors, assets, regions, tripwires, users)
- Performance Testing: Tracker evaluation pipeline with MVP implementation

**Performance and Optimization**

- Memory Leak Fixes: Resolved memory usage issues that caused steady increases over time
- Thread Safety: Improved thread safety in Tracker Service MQTT client during shutdown
- Resource Cleanup: Enhanced cleanup processes for tests and deployments
- Build Optimization: Improved build paths, dependency management, and Docker caching
- Image Size Optimization: Significant reduction in container image sizes through dependency optimization

**Video Analytics Updates**

- Pipeline Optimization: Improved pipeline generation and GPU utilization
- Model Management: Enhanced model downloading and management with updated model sets

**Developer Experience**

- Copilot Integration: Added copilot instructions for enhanced developer experience
- Deployment Scripts: Enhanced deployment scripts with port installation choices

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

:::
hide_directive-->
