# Release Notes: Intel® SceneScape

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
