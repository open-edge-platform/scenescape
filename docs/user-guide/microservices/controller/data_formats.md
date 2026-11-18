<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scene Controller Data Formats

## Message Formats Overview

| Message Format                                                                | Direction | MQTT Topic                                        |
| ----------------------------------------------------------------------------- | --------- | ------------------------------------------------- |
| [Camera Input Message Format](#camera-input-message-format)                   | Subscribe | `scenescape/data/camera/{camera_id}`              |
| [External Source Input Message Format](#external-source-input-message-format) | Subscribe | `scenescape/external/{publisher_id}/{thing_type}` |
| [Data Scene Output Message Format](#data-scene-output-message-format)         | Publish   | `scenescape/data/scene/{scene_id}/{thing_type}`   |
| Point cloud preview (Manager 3D UI)                                           | Publish   | `scenescape/pointcloud/camera/{camera_id}`        |

> **Point cloud preview:** the Manager 3D UI requests a live sensor point cloud with
> `getpointcloud` on `scenescape/cmd/camera/{camera_id}` (same command topic as
> `getimage`). Publishers that support LiDAR/radar visualization reply on
> `scenescape/pointcloud/camera/{camera_id}` with a JSON payload
> (`format: xyz_intensity_f32`, base64 little-endian float32 points, sensor-local
> frame). The Scene Controller does not consume this topic.

The Scene Controller only tracks objects and publishes unregulated per-category output. Sensor
correlation, regulated (rate-controlled) output, and region/tripwire event publishing are owned
by the **Analytics** microservice — see
[Analytics Service Data Formats](../analytics/data_formats.md) for those message formats
(`scenescape/data/sensor/{sensor_id}`, `scenescape/regulated/scene/{scene_id}`,
`scenescape/event/region/{scene_id}/{region_id}/{event_type}`, `scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}`).

## Camera Input Message Format

The Scene Controller subscribes to the MQTT topic `scenescape/data/camera/{camera_id}` and
receives detection metadata from perceptual pipelines. The topic and Manager `Cam` type are
named historically for cameras, but the same contract applies to any perceptual modality
registered as a `Cam` and publishing detections here (RGB, depth, LiDAR or radar detectors
that emit the same object metadata, and similar sensing that uses pose plus optional
intrinsics). Environmental / singleton sensors use a different topic and do not carry
pose or optics. Messages are validated against the `detector` definition in
[metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

### Top-Level Message Fields

| Field            | Type                  | Required | Description                                                                                                                                                                                                                                                                                                                                                     |
| ---------------- | --------------------- | :------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`             | string                |   Yes    | Camera identifier; must match the `{camera_id}` segment in the MQTT topic identifier                                                                                                                                                                                                                                                                            |
| `timestamp`      | string (ISO 8601 UTC) |   Yes    | Acquisition time of the frame                                                                                                                                                                                                                                                                                                                                   |
| `objects`        | object                |   Yes    | Category-keyed map; each value is an array of detections (e.g. `{"person": [...]}`)                                                                                                                                                                                                                                                                             |
| `rate`           | number ≥ 0            |    No    | Camera framerate (frames per second) when the message was produced                                                                                                                                                                                                                                                                                              |
| `sub_detections` | array of string       |    No    | Sub-detection labels run on this frame (e.g. `["license_plate"]`)                                                                                                                                                                                                                                                                                               |
| `intrinsics`     | object                |    No    | Camera intrinsic parameters (`fx`, `fy`, `cx`, `cy`) in sensor pixels. When unlocked, applied as an ephemeral runtime override with extrinsics (not written to Manager). Ignored when Pose locked.                                                                                                                                                              |
| `resolution`     | array or object       |    No    | Sensor dimensions, `[width, height]` or `{"width": width, "height": height}`; positive integers, not thumbnail dimensions. Resolution alone does not change runtime optics; send `intrinsics` (and optional `distortion`) with unlocked frames when updating projection. Ignored when Pose locked.                                                              |
| `distortion`     | object                |    No    | Lens distortion coefficients keyed by name (`k1`, `k2`, `p1`, `p2`, `k3`). When unlocked, applied ephemerally with other MQTT optics. Ignored when Pose locked.                                                                                                                                                                                                 |
| `extrinsics`     | object                |    No    | Per-frame rigid camera pose for unlocked cameras (`pose_locked` is false): `translation` `[x,y,z]`, `rotation` Euler degrees (3) or quaternion `[x,y,z,w]` (4). Scale is not part of camera extrinsics. Declared in `metadata.schema.json`; semantic checks and normalization use runtime `validate_camera_extrinsics`. Ignored when the camera is Pose locked. |

Mobile cameras may include per-frame `extrinsics`. Structurally invalid payloads
fail detector schema validation. Poses that pass the schema but fail semantic
checks (non-finite values, zero-norm quaternion) are logged and ignored. The
observation pose and optics are used for detections, source-camera visibility,
and projected bounds without overwriting registered camera calibration.

The persisted `Cam.pose_locked` controls whether incoming detector-message
extrinsics and optics are used for that sensor, regardless of physical modality.
When unlocked (`pose_locked` is false, the default for new cameras), Controller
and Analytics share one apply path: MQTT `extrinsics` and MQTT `intrinsics` /
`distortion` / `resolution` are ephemeral runtime overrides (never PATCH
Manager). Missing or invalid fields keep the previous observation; accepted live
extrinsics stamp `pose_provenance.class` of `live` (optics-only updates do not).
`pose_provenance` covers pose/extrinsics only — there is no intrinsics or optics
provenance field (see [ADR 18](../../../adr/0018-camera-pose-provenance.md)).
Live pose and its MQTT optics are retained across configuration refreshes while
unlocked. Before the first valid observation, stored calibration initializes the
pose. When locked, incoming MQTT extrinsics and optics are ignored; configuration
refreshes reload stored calibration.

Locking the pose resets the runtime pose on configuration refresh.
Changing back does not resurrect an earlier observed pose. There is no expiry;
camera removal, scene reassignment, or process restart discards runtime retention.
See [Camera Pose Lock](../../api-reference.md#camera-pose-lock) for settings,
archive compatibility, and coordinated upgrade requirements. Accepted live
poses are stamped with `pose_provenance.class` of `live` (typically
`origin: detector.extrinsics`) for Analytics regulated camera entries; see
[ADR 18](../../../adr/0018-camera-pose-provenance.md) and
[Analytics data formats](../analytics/data_formats.md).

Publish pose updates even when object detection is disabled; the server cannot move
a handheld frustum from localization performed only on the device. Pose-only frames
can include empty arrays for the tracked categories, for example
`"objects": {"person": [], "car": []}`.

Supply full sensor `resolution` with camera **registration** and whenever durable
calibrated frame dimensions change via Manager. MQTT resolution/intrinsics do not
persist. For a **new registration only**, pixel intrinsics without dimensions use a
logged, centered-principal-point estimate (`2*cx`, `2*cy`) rather than silently
retaining the 640x480 model default. Conversely, a create that supplies
`resolution` (for example `[1280, 720]` from a demo stream) without `cx`/`cy`
stores a principal point at the frame center (`width/2`, `height/2`, so `640`,
`360` for 1280×720) instead of the legacy `320`, `240` defaults. This is an
estimate, not a substitute for explicit dimensions with off-center calibration.
Existing registrations are not retrospectively inferred.
The 3D UI refreshes durable optics on database notifications and consumes current
optics from camera metadata and image responses without replacing the camera pose.

The DL Streamer demo Compose stack keeps broker port **1883** internal. External
handheld publishers use authenticated MQTT over secure WebSockets through the web
service on port **443**; no external TCP MQTT port is required.

### Detection Object Fields (`objects.<category>[*]`)

For a 2D box, `distance` is depth along the optical axis in metres, not radial
range. A normalized `bounding_box` is already on the normalized image plane:
its coordinates are scaled by depth, not unprojected through intrinsics again.
Only `bounding_box_px` requires pixel unprojection. Native 3D boxes already supply
their camera-frame geometry and pose; an accompanying `distance` is ignored for
both bounding-box forms, without changing their placement or size.
For depth-expanded 2D boxes, inferred cuboid dimensions include the observation
pose's scale. The upright cuboid uses sensor X for width, optical Z for depth,
and sensor Y for height; rotation changes edge directions, not their lengths.
Explicit detection sizes and library size priors remain unchanged.

| Field                  | Type               | Required | Description                                                                                                                                                    |
| ---------------------- | ------------------ | :------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `category`             | string             |   Yes    | Object class label (e.g. `"person"`, `"car"`)                                                                                                                  |
| `bounding_box`         | object             | One of ① | Normalized image-space bounding box (`x`, `y`, `width`, `height`)                                                                                              |
| `bounding_box_px`      | object             | One of ① | Pixel-space bounding box (`x`, `y`, `width`, `height`; optional `z`, `depth`)                                                                                  |
| `translation`          | array[3] of number | One of ① | 3D world position (`x`, `y`, `z`) in metres ③                                                                                                                  |
| `lat_long_alt`         | array[3] of number | One of ① | Geographic position (latitude, longitude, altitude); converted to ECEF internally                                                                              |
| `size`                 | array[3] of number | One of ① | 3D object dimensions (`x`, `y`, `z`) in metres                                                                                                                 |
| `confidence`           | number > 0         |    No    | Inference confidence score for this detection                                                                                                                  |
| `id`                   | integer ≥ 0        |  Yes ②   | Per-frame detection index                                                                                                                                      |
| `rotation`             | array[4] of number |    No    | Object orientation as a quaternion                                                                                                                             |
| `distance`             | number             |    No    | Distance from the camera to the detection in metres                                                                                                            |
| `keypoints`            | array of objects   |    No    | Pose keypoints when a pose estimation model is used; each entry: `{"name": "<keypoint>", "x": <0–1>, "y": <0–1>}` (coordinates normalized to frame dimensions) |
| `keypoint_connections` | array of strings   |    No    | Flat list of keypoint-name pairs defining connections (e.g. `["nose","eye_l","nose","eye_r",...]`); length is always `2 × number_of_connections`               |
| `metadata`             | object             |    No    | Semantic attribute bag (see [Semantic Metadata Fields](#semantic-metadata-fields-objectscategorymetadataattr))                                                 |

> **① Location constraint**: every detection must provide location in exactly one
> of these forms (enforced by the schema's `oneOf`):
>
> - **2D image-based**: `bounding_box` and/or `bounding_box_px` (at least one required;
>   both may be present — if so, `bounding_box` takes precedence)
> - **3D world-space**: `translation` + `size`
> - **Geographic**: `lat_long_alt` + `size` (converted to ECEF `translation` internally)

> **② Schema vs runtime**: The JSON schema currently lists `id` as optional (only
> `category` is in the schema's `required` array). However, the controller accesses
> `id` unconditionally at runtime and will reject detections that omit it. Always
> include `id` in every detection object.

> **③ Height reference**: with
> [experimental observation processor](how-to-configure-tracker.md#height-reference-of-tracked-objects),
> the tracker reads `translation` as the object's centre of mass and publishes tracks at their
> footprint base (`z` minus half the height).

### Semantic Metadata Fields (`objects.<category>[*].metadata.<attr>`)

| Field        | Type          | Required | Description                                                                        |
| ------------ | ------------- | :------: | ---------------------------------------------------------------------------------- |
| `label`      | any           |   Yes    | Detected value for this attribute (e.g. `"Male"` for gender, `true` for a boolean) |
| `model_name` | string        |   Yes    | Name of the model that produced this attribute                                     |
| `confidence` | number [0, 1] |    No    | Confidence score for the detected attribute                                        |

### Example Camera Detection Message

The following example shows a typical message published by a camera pipeline (debug fields
omitted; `embedding_vector` truncated for readability):

```json
{
  "id": "atag-qcam1",
  "timestamp": "2026-03-26T21:01:31.486Z",
  "rate": 10.03,
  "objects": {
    "person": [
      {
        "id": 1,
        "category": "person",
        "confidence": 0.998,
        "bounding_box_px": {
          "x": 419,
          "y": 64,
          "width": 192,
          "height": 411
        },
        "keypoints": [
          { "name": "nose", "x": 0.122, "y": 0.157 },
          { "name": "eye_l", "x": 0.115, "y": 0.136 },
          { "name": "eye_r", "x": 0.16, "y": 0.125 },
          { "name": "shoulder_l", "x": 0.262, "y": 0.276 },
          { "name": "shoulder_r", "x": 0.602, "y": 0.198 }
        ],
        "keypoint_connections": [
          "nose",
          "eye_l",
          "nose",
          "eye_r",
          "eye_l",
          "ear_l",
          "eye_r",
          "ear_r"
        ],
        "metadata": {
          "age": {
            "label": "39",
            "model_name": "age_gender"
          },
          "gender": {
            "label": "Male",
            "model_name": "age_gender",
            "confidence": 0.979
          },
          "reid": {
            "embedding_vector": "<base64-encoded string>",
            "embedding_dimensions": 256,
            "model_name": "torch-jit-export"
          }
        }
      }
    ]
  }
}
```

For the full schema definition, see
[metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

## External Source Input Message Format

The Scene Controller subscribes to `scenescape/external/{publisher_id}/{thing_type}`
(MQTT template parameter name remains `scene_id` in `PubSub` APIs). The path id is
always the **publisher** (configured child scene uid or agent `source_id`). Scenes
attach via consumer-side **bindings**, not by addressing a scene inbox. See
[ADR 16](https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0016-unified-external-source-ingestion.md).

Two payload contracts share the topic, distinguished by `source_id`:

- **Configured child scene** (no `source_id`): `{publisher_id}` is the sending child's
  own id. The controller looks up the child's configured parent and static `cameraPose`.
  Only scenes with a parent publish this hierarchy form; roots do not emit hierarchy
  echoes onto the external topic.
- **Unified external source** (`source_id` present): `{publisher_id}` must equal
  `source_id`. The controller binds the publisher to one or more scenes:
  - **Manual:** `CONTROLLER_EXTERNAL_SOURCE_BINDINGS=publisher_id:scene_uid,...`
  - **Geospatial auto-attach (interim):** `reference_frame: wgs84` attaches to every
    scene with four-corner geospatial calibration (until a footprint/handoff binder)
  - **Cache reuse:** pose omitted → scenes that still hold a live cached pose for
    this publisher
  - **Scene-frame poses:** require a manual binding (and
    `CONTROLLER_TRUSTED_POSITIONING_SOURCES` for acceptance)

Messages with `source_id` are validated against the `external_source` definition in
[metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

This section documents the unified external-source **payload** contract.

To write a converter that maps a source's native output into this contract and
publishes over authenticated MQTT, see
[Publish Observations from an External Source Adapter](../../how-to-guides/publish-external-source-adapter.md).

### External Source Top-Level Fields

| Field        | Type                  |  Required   | Description                                                                                                                                                                                                                                                                   |
| ------------ | --------------------- | :---------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timestamp`  | string (ISO 8601 UTC) |     Yes     | Time the observations (and pose, if present) were acquired                                                                                                                                                                                                                    |
| `source_id`  | string                |     Yes     | Publisher id; must match the topic `{publisher_id}` segment; combined with the bound scene uid to key the pose cache                                                                                                                                                          |
| `objects`    | array                 | Conditional | Source/body-relative observations; required only when `cameras` is omitted. May be empty for a pose-only update. Camera-specific detections belong in their camera entry's `objects` array. See [External Detection Object Fields](#external-detection-object-fields-objects) |
| `pose`       | object                | Conditional | Pose of the source/body origin, used to transform source-level and camera observations into the bound scene (see [External Source Pose Fields](#external-source-pose-fields-pose)); may be omitted to reuse the live cached pose                                              |
| `intrinsics` | object                | Conditional | Legacy single-view calibration for pixel detections in top-level `objects`; newer multi-camera sources put calibration in each camera entry                                                                                                                                   |
| `distortion` | object                |     No      | Optional distortion coefficients paired with top-level `intrinsics` for legacy external pixel detections                                                                                                                                                                      |
| `cameras`    | array                 |     No      | Camera configurations and the observations captured by each camera. Each entry has a stable `id`, body-relative mount, calibration, and its own `objects` array. See [Drone Coordinate and Camera Contract](#drone-coordinate-and-camera-contract)                            |
| `track`      | boolean               |     No      | Applies to source-level and all camera-level objects. `true` (or omitted) routes observations through Scenescape tracking after dual transform; `false` uses source-provided `id` as an exclusive identity claim for Cartesian observations and discards pixel detections     |

### Drone Coordinate and Camera Contract

Each entry in `cameras` describes one camera and owns the observations captured by it.
The controller caches each camera's configuration with the source pose for transform
reuse (internal TTL cache) and projects that configuration onto the platform scene
object's `cameras` field for UI frustums. Mounted-camera pixel detections are
localized with a dual transform (platform pose composed with each camera mount)
and, when `track` is true or omitted, enter Scenescape multi-camera fusion like
ordinary camera input. With `track=false`, pixel detections are discarded (same as
camera input while tracking is off); use Cartesian `translation` observations when
the publisher asserts trusted object identity.

With `track=false`, reusing the same Cartesian object `id` from different publishers
is an identity collision and the later observation is rejected.

For a drone using this contract:

- `pose` places the **drone body origin**, not the camera optical origin, in the scene.
  Use a right-handed body frame: **x forward, y left, z up**. Adapters must convert native
  frames (for example MAVLink forward/right/down) before publishing.
- Top-level `objects[*].translation` is a point in the body frame, in metres. If supplied,
  `objects[*].rotation` describes object-local-to-body orientation.
- A `cameras[*].id` is a stable identifier unique within the source (for example
  `front`). Controllers attribute pixel detections using `source_id:camera_id`.
- `cameras[*].mount` is a rigid transform from the **camera optical frame into the body frame**.
  Optical axes are **x right, y down, z forward**. Its required `translation` is the camera
  optical origin expressed in body metres; its required `rotation` is an active
  optical-to-body quaternion in `(x, y, z, w)` order. Publish a unit quaternion; a zero
  quaternion is rejected. An explicit identity mount means aligned axes, not an automatically
  forward-facing camera.
- `cameras[*].objects[*].translation` is in the camera optical frame, in metres.
  `cameras[*].objects[*].bounding_box_px` is in that camera's image coordinates.
- Intrinsics specify angular geometry for pixel localization and for ideal-pinhole
  UI frustums rendered from the platform object's projected `cameras` field.
  Distortion-aware boundaries, ground footprints, and video projection remain
  follow-on work.

Let `T_scene_body` be the resolved source pose, and `T_body_camera` the camera's fixed mount.
Using homogeneous column vectors:

```text
point_scene    = T_scene_body * point_body
rotation_scene = rotation_scene_body * rotation_body_object
T_scene_camera = T_scene_body * T_body_camera
point_scene    = T_scene_camera * point_camera
```

The mounting transform is used for camera-local observations only. It must **not** be applied
to body-relative top-level object translations. Pixel-box localization uses the composed
`T_scene_camera` transform shown above.
Keep the drone model's origin at the body origin and correct asset axis conventions on
the model child, not by modifying telemetry.

For `reference_frame: wgs84`, `lat_long_alt` uses degrees and altitude in metres above the
WGS84 ellipsoid, as required by the LLA/ECEF conversion; adapters must convert MSL or
relative-flight altitude before publishing. Rotation still maps body axes directly into
the **target scene axes**, even for WGS84 positions. Native ENU/NED attitude is not automatically
aligned by geospatial calibration. The same rotation must not be assumed valid for several
scenes with differently oriented axes.

Sources with no `cameras` array continue to use the source-level observation format; omission
of camera metadata does not imply an identity mount. `camera_mount` at the external-message
top level is not accepted. Every camera entry contains its own complete mount, intrinsics,
stable id, and observations, so calibration for one camera cannot be applied to another. A
pose update from a source already using cameras must include the complete camera list. Messages
without a pose reuse the live source pose; their camera entries still carry the camera
configuration required to interpret those observations. A non-stale camera list may refresh
cached camera state without extending the source-pose expiry.

The controller converts pixel boxes using the corresponding camera's intrinsics and
distortion, then composes the resolved source pose with that camera's mount. Camera-local
Cartesian translations use the same composed transform; top-level Cartesian translations
remain body-relative.

### Platform citizenship (no `data/source` topic)

Dynamic agents remain first-class through the **scene object** pipeline
(`scenescape/data/scene/...` / regulated output), not a parallel retained
`scenescape/data/source/...` product surface. The controller may keep an
**internal** pose/intrinsics TTL cache for transform reuse; that cache is not
a consumer MQTT contract.

- On every accepted message the controller ensures a platform scene object with
  `id == source_id` at the body origin (`translation: [0,0,0]` if synthesized).
  Adapters may publish that object explicitly; otherwise the controller adds it.
  The platform always merges as a trusted identity (`retrack=false`), even when
  message-level `track` is true or omitted for detections.
- Pose-only updates (`objects: []`) still emit/update the platform object and
  advance the tracker so departed detections age out.
- When camera configuration is known (message `cameras[]` or cached config,
  including legacy top-level `intrinsics`), the platform object carries a
  `cameras` array of `{ id, mount, intrinsics, optional distortion }` with
  observations stripped. The 3D view renders child frustums from that
  object-graph state (Bar A); there is no `scenescape/data/source/...` topic.
- Nested ingest `cameras[]` remain the wire encoding for mounts and
  camera-local observations. Frustum lifetime follows platform object presence
  on regulated output (age-out / absence), not retained MQTT tombstones.
- Registered perceptual sensors that should behave as Cams (for example
  handheld devices) use `scenescape/data/camera/{id}` and pose lock /
  provenance — not the external-source topic family.

External-source `pose` and optics are **ephemeral** for every perceptual modality that
publishes on this topic (robots, UWB/RTLS, airborne platforms, LiDAR hubs, and so on):
they live only in the Controller TTL pose cache keyed by `(scene_uid, source_id)` and
are never written to Manager. That matches the unlocked detector-topic policy for
`Cam` sensors — runtime override only — even though the stores differ (TTL cache vs
`SceneModel` observation). Intrinsics provenance is not covered on either path
([ADR 18](../../../adr/0018-camera-pose-provenance.md)).

### External Source Pose Fields (`pose`)

| Field                 | Type               |  Required  | Description                                                                                                                      |
| --------------------- | ------------------ | :--------: | -------------------------------------------------------------------------------------------------------------------------------- |
| `reference_frame`     | string             |    Yes     | `"wgs84"` or `"scene"` — see below                                                                                               |
| `rotation`            | array[4] of number |     No     | Orientation of the source's local origin, as a quaternion (`x`, `y`, `z`, `w`); defaults to identity (`[0, 0, 0, 1]`) if omitted |
| `lat_long_alt`        | array[3] of number | If `wgs84` | Global position of the source's local origin (latitude, longitude, altitude in metres)                                           |
| `translation`         | array[3] of number | If `scene` | Position of the source's local origin in scene-local coordinates (`x`, `y`, `z`)                                                 |
| `position_accuracy_m` | number > 0         |     No     | Estimated accuracy of the reported position in metres, if known                                                                  |
| `provider`            | string             |     No     | Informational label for what produced this pose (e.g. `"agent"`, `"positioning_service"`); not used for authorization            |

`reference_frame` determines how the pose is resolved:

- **`wgs84`** — A global geopose (e.g. from an onboard GNSS/INS). Requires the target scene
  to have valid four-corner geospatial calibration (`map_corners_lla`); the controller converts
  `lat_long_alt` to scene-local coordinates via the scene's LLA/ECEF transform. Rejected with
  `scene_georeference_unavailable` if the scene is not geo-referenced. Any source may publish
  this frame.
- **`scene`** — A pose already expressed in the target scene's local coordinates. This is a
  privileged frame: only accepted from `source_id`s listed in the
  `CONTROLLER_TRUSTED_POSITIONING_SOURCES` environment variable (comma-separated list),
  intended for the Scenescape positioning service. Rejected with `untrusted_scene_pose`
  otherwise. Unset or empty trusts no source (fails closed).

> **Note**: Only position is transformed through the scene's geospatial calibration for
> `wgs84` poses; `rotation` is passed through unrotated, matching existing camera-detection
> `lat_long_alt` handling. Full ENU-to-scene orientation alignment is future work.

### External Detection Object Fields (`objects[*]`)

| Field             | Type               |  Required   | Description                                                                                                                                                                               |
| ----------------- | ------------------ | :---------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `category`        | string             |     Yes     | Category or class of the observed object (e.g. `"person"`, `"vehicle"`)                                                                                                                   |
| `translation`     | array[3] of number | Conditional | Position of the object relative to the source's local origin (`x`, `y`, `z`); exactly one of `translation` or `bounding_box_px` is required                                               |
| `id`              | string             | Conditional | Source-provided identifier; required for Cartesian observations when `track=false`; optional when `track` is true or omitted (pixel detections with `track=false` are discarded)          |
| `rotation`        | array[4] of number |     No      | Rotation of the object as a quaternion (`x`, `y`, `z`, `w`)                                                                                                                               |
| `size`            | array[3] of number |     No      | Object dimensions (`x`, `y`, `z`). Omit for a point observation with no known extent                                                                                                      |
| `confidence`      | number > 0         |     No      | Source-reported confidence for this observation                                                                                                                                           |
| `bounding_box_px` | object             | Conditional | Pixel-space detection box from a camera-like external source using `x/y/width/height`; mutually exclusive with `translation`; localizes via the same pixel-detection path as camera input |
| `metadata`        | object             |     No      | Semantic attribute bag; same structure as camera input (see [Semantic Metadata Fields](#semantic-metadata-fields-objectscategorymetadataattr))                                            |

Unlike camera detections, `size` is optional here: a source that cannot estimate an object's
extent may report a point observation. Point objects (no `size`) remain eligible for
position-based ROI, tripwire, and sensor-tagging analytics, but are excluded from
volume/occupancy/collision analytics.

Report `translation` at the object's centre of mass: with
[experimental observation processor](how-to-configure-tracker.md#height-reference-of-tracked-objects),
tracked objects are published at their footprint base (`z` minus half the height). Objects with
`track=false` bypass the tracker and keep the reported `z`.

The top-level source `track` field determines the tracking mode for detection
objects in the message. When `track` is true or omitted, detections follow the
normal Scenescape tracking path and the controller assigns the published object
`id`, so the source message may omit detection `objects[*].id`. When
`track=false`, Cartesian detections bypass the kinematic tracker/ReID path and
the published object identity is the source-provided `id`; pixel
(`bounding_box_px`) detections are discarded, matching camera input while
tracking is off. The platform self-object (`id == source_id`) is always treated
as a trusted identity regardless of `track`.

When an object includes `bounding_box_px`, it is treated as a camera-style pixel detection rather
than as a source-local Cartesian observation. Do not send both `translation` and `bounding_box_px`
on the same object. In that case:

- A usable source `pose` and top-level `intrinsics` must be available from this message or from
  the live `(scene_id, source_id)` cache entry. If either cannot be resolved, the message is
  dropped and no objects from it are ingested.
- Scenescape computes the object location with the same pixel-to-location algorithm used for camera
  detections.
- With `track=true` or when `track` is omitted, the localized detection enters normal Scenescape
  tracking after the platform/mount dual transform. With `track=false`, pixel detections are
  discarded; they do not become trusted-identity tracks.

### Pose Caching and Message Ordering

A resolved pose is cached per `(scene_id, source_id)` for `30` seconds. Camera `intrinsics`
(and optional `distortion`) for pixel detections are stored on the same cache entry and preserved
across pose refreshes until replaced or the entry expires. Subsequent messages from the same
source may omit `pose` and/or `intrinsics` to reuse the cached values; a message with a `pose`
and an empty `objects` array updates the cache and still materializes the
platform scene object at the body origin. Every successfully resolved message,
including one with zero detections, still advances the bound scene's tracker for
that object category: an accepted empty update is an empty measurement for
detections (so they age out of the published scene state) while the platform
remains present. Messages with
a `timestamp` older than the currently cached pose are treated as out-of-order and ignored in
favor of the newer cached transform. If no usable transform can be resolved (no pose supplied and
nothing cached, or the cached pose has expired), the message is dropped without ingesting
objects. Pixel detections equally require usable intrinsics (from the message or cache).
Rejection reasons (logged, not published) include:

| Reason                           | Cause                                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------------- |
| `no_pose_available`              | No `pose` supplied and no prior cached transform for this `(scene_id, source_id)`           |
| `pose_expired`                   | No `pose` supplied and the cached transform is older than the cache TTL                     |
| `no_intrinsics_available`        | Pixel detections present, no `intrinsics` supplied, and none cached on the live pose entry  |
| `invalid_intrinsics`             | `intrinsics` failed construction                                                            |
| `cameras_required`               | Pose update for a multi-camera source omitted the complete `cameras` list                   |
| `scene_georeference_unavailable` | `reference_frame: wgs84` but the target scene has no valid geospatial calibration           |
| `untrusted_scene_pose`           | `reference_frame: scene` from a `source_id` not in `CONTROLLER_TRUSTED_POSITIONING_SOURCES` |
| `unsupported_reference_frame`    | `reference_frame` is not `wgs84` or `scene`                                                 |
| `invalid_pose`                   | `pose` failed schema validation or transform construction                                   |

### Source-Identity Trust for Untracked Objects, with Collision Detection

When an external source message sets `track` to `false`, Cartesian observations
bypass Scenescape's kinematic multi-object tracker/ReID association and merge
through the already-tracked path used for child scenes with `retrack=false`.
The source-provided `id` is used as the published object identity. Pixel
(`bounding_box_px`) detections in the same message are discarded — the same
behavior as camera input while tracking is off — because there is no
cross-camera identity authority for raw detector boxes.

Two different sources publishing the same source-provided Cartesian `id` could
silently merge distinct objects. The controller therefore allows only one source to hold a live
claim on that `id` within a `(scene, category)` pair. A colliding object is dropped and logged;
other Cartesian objects from the same message are still ingested.

Identity is trusted based on the `source_id` and `id` values in the payload, not a
cryptographically verified per-device credential. Scenescape's current MQTT authentication does
not bind individual publishers to individual source IDs (see
[ADR 16](https://github.com/open-edge-platform/scenescape/blob/main/docs/adr/0016-unified-external-source-ingestion.md#future-work)).
A publisher that can reach the broker can claim either of these values.

### Tracked External Objects Use Controller-Assigned IDs

When an external source message sets `track` to `true` or omits it, each object is processed
as a normal Scenescape detection. Mounted-camera pixel detections are first localized with
the dual transform (platform pose composed with each camera mount), then enter the
kinematic tracker/ReID path. The controller assigns the published track `id`. On this path,
source-provided `objects[*].id` is optional and treated only as source metadata for the
incoming observation, not as the final published track identity.

### Choosing a `source_id` (Self-Identification for Agents)

`source_id` is not provisioned or registered anywhere in Scenescape ahead of time — unlike a
camera or sensor `id`, which must match a scene/sensor already configured in the database, an
external source simply announces itself by choosing a `source_id` string and publishing with it.
For messages using `track=false` with Cartesian observations, choose a persistent
`source_id` and per-object `id`. That `id` becomes the published identity and must
not collide with another publisher's live identity. Mounted-camera pixel
detections should use `track=true` (or omit `track`) so Scenescape can fuse them
after the dual transform; `track=false` discards those pixels. For tracked
messages, a stable source-provided object `id` can improve observation
correlation even though Scenescape assigns the published identity. The
deployer/integrator should choose values that are:

- **Persistent** — stable across process restarts and reboots, so a track's identity (and any
  cached pose) is recognized as the same source/object next time it publishes, rather than
  treated as a brand-new one.
- **Unique** — will not collide with another source's identifier on the same scene/broker.

Recommended choices, in order of preference:

1. **A hardware-rooted identifier already unique to the device** — a serial number, a
   TPM-backed device UUID, or (for a UWB/RTLS tag) the tag's own hardware/network ID. This is
   the strongest option because it is normally immutable and cannot be trivially changed by
   reconfiguring software.
2. **The primary network interface's MAC address** — a practical, widely available choice for
   robots, drones, and other networked devices; it is unique per interface and typically stable
   across reboots. This mirrors the convention already used for sensor identifiers elsewhere in
   Scenescape (see the [Sensor Input Message Format](../analytics/data_formats.md#sensor-input-message-format) example,
   `02:42:ac:11:00:05.1`).
3. **A deployer-assigned static name** (for example `"drone-1"`, `"forklift-north-3"`) — acceptable
   as long as it is provisioned once per physical device and not regenerated on every boot or
   process restart.

**Do not** use a randomly generated value (for example a fresh UUID minted at process startup)
as `source_id`: it defeats pose-cache reuse across restarts. For `track=false`, do not use a
random or resettable object `id`, because each restart creates a new published identity or may
reuse a stale identity for a different physical object. Prefer hardware-rooted or MAC-based
identifiers specifically to avoid this.

**If a robot or drone reports itself as a tracked object** (for example, to visualize the
platform itself in the scene alongside objects it observes), use the same persistent identifier
described above for that object's `id` — typically the platform's own MAC address, serial
number, or device UUID — rather than a value tied to the current process/session.

### Example: Agent Publishing a Global Pose and Observations

```json
{
  "timestamp": "2026-03-26T21:01:31.486Z",
  "source_id": "drone-1",
  "pose": {
    "reference_frame": "wgs84",
    "lat_long_alt": [37.38688947, -121.96410521, 8.07],
    "rotation": [0, 0, 0, 1]
  },
  "objects": [
    {
      "id": "track-42",
      "category": "vehicle",
      "translation": [3.2, -1.4, 0.0],
      "confidence": 0.91
    }
  ]
}
```

### Example: Drone with Multiple Cameras

Each camera carries its own calibration and detections. Omit `track` (or set
`track: true`) so each camera's pixel boxes are dual-transformed into the scene
and fused by Scenescape tracking. Detector-local `id` values are optional hints
only; they are not cross-camera identity. With `track: false`, these pixel
detections would be discarded.

```json
{
  "timestamp": "2026-03-26T21:01:31.486Z",
  "source_id": "drone-1",
  "pose": {
    "reference_frame": "wgs84",
    "lat_long_alt": [37.38688947, -121.96410521, 8.07],
    "rotation": [0, 0, 0, 1]
  },
  "cameras": [
    {
      "id": "front",
      "mount": {
        "translation": [0.2, 0, 0.1],
        "rotation": [-0.5, 0.5, -0.5, 0.5]
      },
      "intrinsics": { "fx": 905, "fy": 910, "cx": 600, "cy": 350 },
      "objects": [
        {
          "category": "person",
          "bounding_box_px": { "x": 400, "y": 120, "width": 80, "height": 210 }
        }
      ]
    },
    {
      "id": "rear",
      "mount": {
        "translation": [-0.2, 0, 0.1],
        "rotation": [0.5, -0.5, 0.5, 0.5]
      },
      "intrinsics": { "fx": 820, "fy": 825, "cx": 640, "cy": 360 },
      "objects": [
        {
          "category": "person",
          "bounding_box_px": { "x": 700, "y": 130, "width": 76, "height": 206 }
        }
      ]
    }
  ]
}
```

### Example: Positioning Service Publishing a Scene-Local Pose

Requires `source_id` (e.g. `"positioning-service-1"`) to be listed in
`CONTROLLER_TRUSTED_POSITIONING_SOURCES`.

```json
{
  "timestamp": "2026-03-26T21:01:31.486Z",
  "source_id": "positioning-service-1",
  "pose": {
    "reference_frame": "scene",
    "translation": [5.0, 2.0, 0.0],
    "rotation": [0, 0, 0, 1],
    "provider": "positioning_service"
  },
  "objects": [
    { "id": "person-7", "category": "person", "translation": [1.0, 0.5, 0.0] }
  ]
}
```

### Example: Pose-Only Update and Point-Object Observation

A pose-only update refreshes the cached transform and still materializes the
platform scene object (`id` matching `source_id`) at the body origin:

```json
{
  "timestamp": "2026-03-26T21:01:41.486Z",
  "source_id": "drone-1",
  "pose": {
    "reference_frame": "wgs84",
    "lat_long_alt": [37.38688947, -121.96410521, 8.07],
    "rotation": [0, 0, 0, 1]
  },
  "objects": []
}
```

A subsequent message reuses the cached pose and reports a point object (no `size`):

```json
{
  "timestamp": "2026-03-26T21:01:42.486Z",
  "source_id": "drone-1",
  "objects": [
    { "id": "person-3", "category": "person", "translation": [1.0, 0.5, 0.0] }
  ]
}
```

## Common Output Track Fields

> **Note**: Sensor input (`scenescape/data/sensor/{sensor_id}`) is no longer consumed by the
> Scene Controller. Sensor correlation is owned by the **Analytics** microservice — see
> [Sensor Input Message Format](../analytics/data_formats.md#sensor-input-message-format)
> and [Singleton Sensor Data](../../how-to-guides/integrate-cameras-and-sensors.md#singleton-sensor-data)
> for the sensor input message format and how tagged data appears on scene objects.

All Scene Controller output messages include an `objects` array of tracked objects. Each
tracked object contains the following fields:

| Field                  | Type                       | Description                                                                                                                                                                                                                                                      |
| ---------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                   | string                     | Persistent scene-object identifier; assigned by Scenescape for tracked detections, and may be source-provided or a controller-scoped shared identity for `track=false` external observations                                                                     |
| `type`                 | string                     | Object type label; same value as `category` (e.g. `"person"`)                                                                                                                                                                                                    |
| `category`             | string                     | Object class label (e.g. `"person"`)                                                                                                                                                                                                                             |
| `confidence`           | number                     | Inference confidence of the most recent contributing detection                                                                                                                                                                                                   |
| `translation`          | array[3] of number         | 3D world position (`x`, `y`, `z`) in metres                                                                                                                                                                                                                      |
| `size`                 | array[3] of number         | 3D object dimensions (`x`, `y`, `z`) in metres                                                                                                                                                                                                                   |
| `velocity`             | array[3] of number         | Velocity vector (`x`, `y`, `z`) in metres per second                                                                                                                                                                                                             |
| `rotation`             | array[4] of number         | Orientation quaternion                                                                                                                                                                                                                                           |
| `visibility`           | array of string            | Camera IDs currently observing this object                                                                                                                                                                                                                       |
| `source_ids`           | array of strings, optional | External publishers that have contributed observations during this active track's lifetime. Retained until the track expires; this is provenance, not camera visibility                                                                                          |
| `keypoints`            | array of objects           | Pose keypoints propagated from detections when available; each entry uses `{"name": "<keypoint>", "x": <0-1>, "y": <0-1>}` coordinates normalized to frame dimensions                                                                                            |
| `keypoint_connections` | array of strings           | Flat list of keypoint-name pairs defining the skeleton edges (e.g. `["nose","eye_l","nose","eye_r",...]`); length is always `2 x number_of_connections`                                                                                                          |
| `regions`              | object                     | Map of region/sensor IDs to membership metadata. **Never populated by the Scene Controller** — added by the Analytics microservice when it enriches this data; see note below.                                                                                   |
| `sensors`              | object                     | Map of sensor IDs to timestamped readings (`{id: [[timestamp, value], ...]}`). **Never populated by the Scene Controller** — added by the Analytics microservice; see note below.                                                                                |
| `similarity`           | number or null             | Similarity/distance value to the matched ReID embedding in the configured vector database; higher-is-better for `COSINE`; lower is better for `L2`. `null` when ReID is still collecting embeddings, when no database match was found, or when ReID is disabled. |
| `reid_state`           | string                     | Re-ID processing state for the object. One of: `pending_collection`, `query_no_match`, `matched`, `reid_disabled`                                                                                                                                                |
| `previous_ids_chain`   | array or absent            | History of UUID reassignments for this track. Each element is `{"id": "<uuid>", "timestamp": "<ISO 8601>", "similarity_score": <number or null>}`. Present only when the object has been re-identified at least once; omitted otherwise.                         |
| `first_seen`           | string (ISO 8601)          | Timestamp when the track was first created                                                                                                                                                                                                                       |
| `metadata`             | object                     | Semantic attributes propagated from camera detections; present when visual analytics (e.g. age, gender, Re-ID) are configured. Same attribute structure as camera input. See note below.                                                                         |
| `camera_bounds`        | object                     | Per-camera pixel bounding boxes (`{camera_id: {x, y, width, height, projected}}`) where `projected=false` means detector-provided pixel bbox and `projected=true` means computed projection; may be empty (`{}`) when no camera currently observes the track     |
| `association_window`   | object or absent           | Association gate geometry for UI visualization. Present when the producer publishes gate parameters. See note below.                                                                                                                                             |

> **Note on `metadata` in track objects**: Each attribute follows the structure
> `{label, model_name, confidence?}` — identical to [Semantic Metadata Fields](#semantic-metadata-fields-objectscategorymetadataattr)
> in camera input. The `reid` attribute is a special case: in scene output
> `reid.embedding_vector` is a **2D float array** (`[[...numbers...]]`), whereas in
> camera input it is a base64-encoded string. `metadata` is absent when no semantic
> analytics pipeline is configured.

> **Note on keypoint propagation**: `keypoints` and `keypoint_connections` are
> optional pass-through fields from object detections. They are included in output
> objects when present on the contributing detection data.

> **External observation provenance:** `objects[*].source_ids` lists external publishers
> that contributed observations to the active track and is preserved through Analytics
> regulated and event output. It is separate from `visibility`, which is calculated from
> configured camera geometry: a drone can report an object even when that object's
> `visibility` is empty. The set accumulates for the lifetime of the track and is not
> cleared when one source stops reporting; it does not imply that an object lies inside a
> source camera's frustum. Native camera tracks do not receive this field automatically.

External Cartesian observations are transformed independently for each bound scene:
translation is transformed once, and an explicitly supplied object rotation is composed
as `rotation_scene_source * rotation_source_object`. The fixed camera mount does not
affect body-relative translations. No object orientation measurement is invented when
rotation is omitted. Untracked objects continue to preserve publisher-supplied ids,
subject to the existing identity-collision checks.

> **Note on `similarity`**: This field holds the metric value returned by the ReID
> backend in `_distance` and is evaluated by the controller using configured metric semantics.
> For `COSINE` (normalized vectors with backend IP/DOT), value must be above `similarity_threshold`; for distance-style metrics such as `L2`,
> value must be below `similarity_threshold`.
> A value of `null` means either the ReID query has not been submitted yet
> (`pending_collection`), the query found no match below the configured
> `similarity_threshold` (`query_no_match`), or ReID is disabled (`reid_disabled`).

> **Note on `reid_state` values**:
>
> - `pending_collection`: Re-ID embedding collection is in progress; query has not been submitted yet.
> - `query_no_match`: Query was submitted but no database match was found.
> - `matched`: Query found a database match and the object was re-identified.
> - `reid_disabled`: Re-ID is disabled for this object lifecycle (for example due to runtime disablement).

> **Note on `regions`/`sensors`**: These fields are added by the Analytics microservice
> when it consumes `scenescape/data/scene/{scene_id}/{thing_type}` and republishes enriched,
> regulated, and region/tripwire-event output. `regions` defaults to `{id: {entered: timestamp}}`
> and gains a live `dwell` value for objects currently inside a region:
> `{id: {entered: timestamp, dwell: seconds}}`. Exit records expose the final dwell time
> separately as `{"object": <track>, "dwell": <seconds>}` in the top-level `exited` array.
> See [Regulated Scene Output Message Format](../analytics/data_formats.md#regulated-scene-output-message-format)
> for full format details.

> **Note on `association_window`**: Produced by the Scene Controller and Tracker service so
> the Manager 2D/3D UI can draw association gates. Shape depends on `association.method`:
>
> - `euclidean` → `{method, shape: "circle", radius_m}` where `radius_m` is `max_radius_m`; without
>   it, the Scene Controller's gate, the average `tracking_radius` of the frame's objects
> - `position_mahalanobis` → `{method, shape: "ellipse", semi_major_m, semi_minor_m, angle_rad}`
>   from the χ² contour of the track's predicted XY measurement covariance (`S_pred`), the XY shadow
>   of the track's gate: χ²(`gate_probability`, 3) for a track with measured z, χ²(`gate_probability`, 2)
>   without; each semi-axis clipped to `max_radius_m` so the drawn region stays inside the hard association ceiling
>
> `angle_rad` is the major-axis orientation in the scene XY plane (radians from +X toward +Y),
> defined modulo π: the ellipse is the same after a half turn.
> The window has no centre of its own: the UIs draw it at the object's published (corrected)
> `translation`, while the gate is centred on the predicted position. The drawing is exact for a
> track without a detection in that frame and off by the Kalman correction otherwise.
> Analytics passes the field through on regulated scene output when present.

## Data Scene Output Message Format

Published on MQTT topic: `scenescape/data/scene/{scene_id}/{thing_type}`

The Scene Controller publishes unregulated (raw) tracking results, one message per object
category per scene publication cycle. Each message contains the current state of all tracked
objects of that category.

This is a scene-level snapshot, not a copy of the input publisher envelope. The top-level
`source_id`, `pose`, `track`, `intrinsics`, `distortion`, and message `cameras` fields
are omitted. The platform appears here as a normal scene object (`id` matching
`source_id`). When camera configuration is known, that platform object includes a
`cameras` array (`id`, `mount`, `intrinsics`, optional `distortion`) used for
object-graph frustum rendering. Per-object contributing publishers are represented
by `source_ids`.

### Data Scene Top-Level Fields

| Field                    | Type                  | Description                                                                     |
| ------------------------ | --------------------- | ------------------------------------------------------------------------------- |
| `id`                     | string                | Scene identifier (UUID)                                                         |
| `timestamp`              | string (ISO 8601 UTC) | Publication timestamp                                                           |
| `name`                   | string                | Scene name                                                                      |
| `rate`                   | number                | Current scene processing rate in Hz                                             |
| `unique_detection_count` | integer               | Cumulative count of unique detections since scene start                         |
| `objects`                | array                 | Tracked objects (see [Common Output Track Fields](#common-output-track-fields)) |

### Example Data Scene Message

```json
{
  "id": "302cf49a-97ec-402d-a324-c5077b280b7b",
  "timestamp": "2026-03-26T20:49:59.642Z",
  "name": "Queuing",
  "rate": 9.984,
  "unique_detection_count": 91,
  "objects": [
    {
      "id": "65d49fa0-a855-46f8-bb41-4e92102c7c47",
      "category": "person",
      "type": "person",
      "confidence": 0.999,
      "translation": [2.463, 3.61, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [-0.045, 0.012, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "metadata": {
        "age": { "label": "32", "model_name": "age_gender" },
        "gender": {
          "label": "Male",
          "model_name": "age_gender",
          "confidence": 0.904
        },
        "reid": {
          "embedding_vector": "<embedding_dimensions-element float array>",
          "embedding_dimensions": 256,
          "model_name": "torch-jit-export"
        }
      },
      "camera_bounds": {
        "atag-qcam1": {
          "x": 169,
          "y": 4,
          "width": 96,
          "height": 168,
          "projected": false
        }
      },
      "similarity": null,
      "reid_state": "pending_collection",
      "first_seen": "2026-03-26T20:49:49.339Z"
    }
  ]
}
```

> **Note**: The example above omits `regions` and `sensors`, which the Scene Controller never
> populates on this topic (see [Common Output Track Fields](#common-output-track-fields) above).
> The Analytics microservice consumes this topic and republishes enriched, regulated
> (rate-controlled), and region/tripwire-event output — including `regions` and `sensors` on
> each object. See [Analytics Service Data Formats](../analytics/data_formats.md) for the
> `scenescape/regulated/scene/{scene_id}`, `scenescape/event/region/{scene_id}/{region_id}/{event_type}`,
> and `scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}` message formats.
