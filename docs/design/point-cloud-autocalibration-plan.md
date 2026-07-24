# Plan for integration of point-cloud registration algorithm into AutoCalibration service

Your task is to assist me in the initial implementation of point-cloud based
autocalibration. The capability is **sensor-agnostic**: the input is a point cloud,
regardless of which perceptual sensor produced it (e.g. LiDAR, depth camera, stereo rig,
or a photogrammetry pipeline). LiDAR is one motivating use case, defined by the JIRA Epic
exported as file: docs/jira/ITEP-92856.xml, but nothing in this design is tied to a
specific sensor type.

The scope of the task is roughly described in the JIRA story exported as file
docs/jira/ITEP-93047.xml and should include:
- internal conversion of Scene mesh to point cloud on registration (GLB or PLY format for Scene 3D model are supported currently)
- implementation of the point-cloud registration (sensor localization) algorithm in the basic case of complete overlap between the sensor point cloud and the Scene point cloud
- extending the existing autocalibration API with a point-cloud registration API
- unit tests and API-level service tests

Out of scope: 
- end to end flows (integration with Scene Manager and analytics pipeline)
- support for partial overlap between the sensor point cloud and the Scene
- support for large point-clouds and high-density sensors
- point cloud and mesh data generation (will be generated in a separate task)

## Generic Guidelines

- Understand and follow the existing conventions used for API and code design.
- Follow best coding practices
- Ask for approval / guidance when the provided instructions are not consistent or clear enough to make informed decisions

## Design Decisions

These decisions are settled and drive the steps below:

1. **API shape** — Add a new resource group `/v1/point-cloud-sensors/{sensorId}/registration`
   plus a new **point-cloud registration strategy** that follows the existing AprilTag /
   Markerless controller pattern. `sensorId` identifies any point-cloud-producing sensor
   and is not tied to a sensor type. Scene-mesh-to-point-cloud conversion happens
   internally as part of the registration flow.
2. **Sensor point cloud input** — Supplied as a base64-encoded point cloud (PLY or PCD)
   in the POST request body, validated against size limits and format magic bytes
   (mirrors the existing image-data validation).
3. **Registration algorithm** — Use **Open3D CPU Generalized ICP (GICP)** with voxel
   downsampling and a point-to-plane ICP refinement pass. `open3d-cpu[headless]==0.19.0`
   is already a dependency, so **no new dependencies** are introduced. PCL + oneAPI
   Intel-GPU acceleration is deferred to a separate research spike (see
   *Further Considerations*).
4. **Manager coupling** — Fully **decoupled**. No Manager data-model or UI changes. The
   `sceneId` is provided per request; the Scene 3D mesh is fetched read-only from the
   Manager REST API by id (as today); the sensor identity and point cloud are supplied in
   the request body.
5. **Scene point-cloud cache** — **Lazy build**: the scene point cloud is generated from
   the scene mesh on the first registration call for that scene and cached; invalidated
   when the scene map changes.
6. **Canonical point-cloud format** — **PCD (`binary_compressed`)** is the canonical
   serialization format for cached scene point clouds and internal persistence.
   Registration runs on the in-memory Open3D `PointCloud` (float64 compute); PCD is only
   the persistence boundary. The API **accepts both PLY and PCD** on input, normalized to
   the in-memory cloud. Coordinates are stored **float32 in meters in the local scene
   frame** (≤1 mm quantization to ~8 km, ≤1 cm to ~84 km from the origin — global
   geodetic/ECEF coordinates must not be stored in this frame); normals (and optional
   color) are persisted in the PCD. Cached scene clouds follow the existing
   **file-on-media-volume + path/timestamp-in-DB** convention, keeping the database
   metadata-only (matching how `map`, `polycam_data`, and `global_descriptor_file` are
   stored today); a future DB-blob path is possible but not required.

## Steps

### Phase 1 — Registration algorithm core (no service wiring)

1. Add `autocalibration/src/point_cloud_registration.py` with a
   `PointCloudRegistration` class responsible for:
   - Decoding and validating a base64 PLY/PCD payload into an Open3D point cloud.
   - Converting a scene mesh (GLB or PLY) to a point cloud by sampling
     (`sample_points_uniformly` / `sample_points_poisson_disk`), reusing
     `scene_common.mesh_util` helpers (`extractTriangleMesh`, `extractMeshFromGLB`,
     `extractMeshFromPointCloud`).
   - Serializing / caching the scene point cloud as PCD (`binary_compressed`, float32
     coordinates in meters, normals persisted).
   - Preprocessing (voxel downsampling, normal estimation).
   - Running Generalized ICP (`o3d ... registration_generalized_icp`) with a
     point-to-plane `registration_icp` refinement, returning the 4x4 transform,
     fitness, and inlier RMSE.
2. Add a `meshToPointCloud` helper (in `scene_common/src/scene_common/mesh_util.py` or
   local to the new module) reusing `extractTriangleMesh`.
3. Add a `POINTCLOUD = 'PointCloud'` constant to `scene_common/src/scene_common/options.py`
   used only for strategy keying (not added to the Manager DB choices, to keep the
   service decoupled).

### Phase 2 — Registration strategy and context wiring

4. Add `autocalibration/src/point_cloud_registration_controller.py` with
   `PointCloudRegistrationController(CameraCalibrationController)` (template:
   `atag_camera_calibration_controller.py`):
   - `process_scene_for_calibration` lazily builds and caches the scene point cloud.
   - `generate_calibration` registers the incoming sensor cloud against the cached scene
     cloud and returns the transform result.
   - `is_map_updated` / `reset_scene` invalidate the cached scene point cloud.
5. Register the strategy in `auto_camera_calibration_context.py`
   (`scene_strategies["PointCloud"]`), and add a registration thread wrapper plus a
   `process_point_cloud_registration` method mirroring the camera-calibration path; store
   the result keyed by `sensorId` and emit a `point_cloud_registration_result` Socket.IO
   event.

### Phase 3 — REST and WebSocket API

6. In `auto_camera_calibration_api.py`:
   - Add `POST /v1/point-cloud-sensors/<sensorId>/registration` (body: `sceneId`,
     `pointcloud` base64, optional `format`, optional `initial_transform`); validate
     input, fetch the scene by `sceneId`, dispatch the point-cloud strategy directly (not
     via `scene.camera_calibration`), run asynchronously and return `202`.
   - Add `GET /v1/point-cloud-sensors/<sensorId>/registration` to poll status and, on
     success, return the transform, fitness, and inlier RMSE.
   - Add a `_validate_pointcloud` helper (size limit, PLY/PCD magic bytes) and the
     matching error classes.
   - Register a Socket.IO `register_point_cloud_sensor` event and the result emit.
7. Extend `autocalibration/src/autocalibration_client.py` with `registerPointCloud` and
   `getPointCloudRegistrationStatus`.

### Phase 4 — Tests

8. Add unit tests under `tests/sscape_tests/pointcloud/` (conftest following
   `tests/sscape_tests/markerless/conftest.py`):
   - Mesh-to-point-cloud conversion for GLB and PLY.
   - Recovery of a known synthetic transform within tolerance (positive).
   - Rejection of empty / degenerate / malformed clouds (negative).
   - A marked performance test validating the KPI (>1M points registered in <30s).
9. Add API-level scenarios to `tests/api/scenarios/autocalibration_api.json` (success,
   unknown `sceneId` -> 404, invalid point cloud -> 400) driven via
   `AutoCalibrationClient`.

### Phase 5 — Documentation and licensing

10. Update the auto-calibration docs:
    `docs/user-guide/microservices/auto-calibration/auto-calibration.md`,
    `.../api-reference.md`, and the OpenAPI spec
    `.../_assets/autocalibration-api.yaml`.
11. Update `autocalibration/Agents.md` and this working design document.
12. Add SPDX headers (`(C) 2026 Intel Corporation`, `Apache-2.0`) to all new files and
    keep 2-space indentation (`make indent-check`).

## Verification

- `make rebuild-autocalibration`, then start the service.
- `pytest tests/sscape_tests/pointcloud/` (unit + KPI performance test).
- Run the new API scenarios through the `tests/api` harness.
- Manual smoke test: POST a base64 PLY to
  `/v1/point-cloud-sensors/{id}/registration`, poll the GET endpoint, and verify the
  returned transform against a known ground-truth pose.
- `make indent-check` and REUSE license lint.

## Further Considerations

1. **GPU acceleration (PCL + oneAPI)** — Deferred to a separate research spike. Findings:
   PCL's GPU registration module is CUDA-only (no Intel oneAPI path); Open3D's SYCL
   Intel-GPU support currently ships only as a preview Python 3.10 wheel and is not part
   of the pinned `open3d-cpu` package. The CPU GICP foundation meets the KPI and keeps the
   dependency surface unchanged.
2. **Partial overlap and high-density sensors** — Explicitly out of scope for this
   foundation; the registration module should be structured so a coarse global
   registration (feature-based) stage can be added later.
3. **Sensor ↔ scene association** — Provided via `sceneId` in the request body now; a
   future Manager point-cloud sensor entity is out of scope.

## Test Data Requirements

Point cloud and mesh test data are generated by a separate task. The input specification
for that task is documented in
`docs/design/point-cloud-autocalibration-test-data-spec.md`.

## References

- Autocalibration API and flows: docs/design/autocalibration-api-flow-summary.md
- Lidar calibration Epic: docs/jira/ITEP-92856.xml
- Initial Story: docs/jira/ITEP-93047.xml
- Test data specification: docs/design/point-cloud-autocalibration-test-data-spec.md
