# Release Notes: Scenescape

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
- Controller Analytics Mode: New analytics-only mode for the controller with schema validation

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
