<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Observation Processor Service

The Observation Processor is an optional gRPC service that converts a camera
frame's 2D detections into world-space measurements for scene tracking. It
combines the `frustum_gaussian` projection library with optional scene-mesh
conditioning from `observation_conditioning`.

The service is available through the Docker Compose
`observation-processor` profile.

## Processing

For each `ProcessDetections` request, the service uses the scene and camera IDs
to load static configuration from the Manager REST API. It obtains camera
calibration, image resolution, the scene mesh, and category size priors from the
object library. The service undistorts the image box, estimates a 3D Gaussian
measurement, and optionally conditions depth against the scene mesh.

The `mode` field selects the processing path:

- `AUTO`: use full mesh conditioning when the scene has a GLB mesh; otherwise
  return frustum-only measurements.
- `FULL`: project detections and condition them against the scene mesh. The
  request fails with `FAILED_PRECONDITION` if the scene has no GLB mesh.
- `FRUSTUM_ONLY`: skip amodal mesh conditioning. Per-detection `project_to_map`
  can still use the mesh when one is available.

The service warms camera geometry and mesh data before reporting ready. Manager
database-change events schedule cache refreshes; requests continue using the
last successfully warmed snapshot while a replacement is loading or if a
refresh fails.

## gRPC API

The service exposes `scenescape.observation_processor.v1.ObservationProcessorService`
with the unary `ProcessDetections` RPC and the standard gRPC health service. The
request includes a scene ID, camera ID, timestamp, conditioning mode, and an
ordered list of detections. The response contains one measurement status per
detection and, when requested, frustum and amodal diagnostics.

The protobuf contract is maintained in
[`observation_processor.proto`](../../../../observation_processor/proto/observation_processor.proto).
Errors apply to the whole frame:

| Status                | Meaning                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------ |
| `INVALID_ARGUMENT`    | Required request data is missing or invalid.                                                                 |
| `NOT_FOUND`           | The scene or camera is unknown or not associated.                                                            |
| `FAILED_PRECONDITION` | Camera calibration is invalid, an asset has invalid size dimensions, or `FULL` mode requires a missing mesh. |
| `UNAVAILABLE`         | No warmed configuration is available or the configuration store cannot be reached.                           |
| `INTERNAL`            | Projection or conditioning failed.                                                                           |

See the [build guide](get-started/build-from-source.md) for building and
starting the optional Compose service. Service configuration variables and a
sample client command are documented in the
[service README](../../../../observation_processor/README.md).

## Deployment Status

The Observation Processor is currently available only through Docker Compose.
A Helm chart for this service has not been created yet, so it is not deployable
through the Scenescape Kubernetes chart.
