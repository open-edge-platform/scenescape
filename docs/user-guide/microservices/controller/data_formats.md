<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scene Controller Data Formats

## Message Formats Overview

| Message Format                                                                  | Direction | MQTT Topic                                                        |
| ------------------------------------------------------------------------------- | --------- | ----------------------------------------------------------------- |
| [Camera Input Message Format](#camera-input-message-format)                     | Subscribe | `scenescape/data/camera/{camera_id}`                              |
| [Sensor Input Message Format](#sensor-input-message-format)                     | Subscribe | `scenescape/data/sensor/{sensor_id}`                              |
| [External Source Input Message Format](#external-source-input-message-format)   | Subscribe | `scenescape/external/{scene_id}/{thing_type}`                     |
| [Data Scene Output Message Format](#data-scene-output-message-format)           | Publish   | `scenescape/data/scene/{scene_id}/{thing_type}`                   |
| [Regulated Scene Output Message Format](#regulated-scene-output-message-format) | Publish   | `scenescape/regulated/scene/{scene_id}`                           |
| [Region Event Output Message Format](#region-event-output-message-format)       | Publish   | `scenescape/event/region/{scene_id}/{region_id}/{event_type}`     |
| [Tripwire Event Output Message Format](#tripwire-event-output-message-format)   | Publish   | `scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}` |

## Camera Input Message Format

The Scene Controller subscribes to the MQTT topic `scenescape/data/camera/{camera_id}` and
receives camera detection metadata from visual analytics pipelines. Messages are validated
against the `detector` definition in
[metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

### Top-Level Message Fields

| Field            | Type                  | Required | Description                                                                                                                         |
| ---------------- | --------------------- | :------: | ----------------------------------------------------------------------------------------------------------------------------------- |
| `id`             | string                |   Yes    | Camera identifier; must match the `{camera_id}` segment in the MQTT topic identifier                                                |
| `timestamp`      | string (ISO 8601 UTC) |   Yes    | Acquisition time of the frame                                                                                                       |
| `objects`        | object                |   Yes    | Category-keyed map; each value is an array of detections (e.g. `{"person": [...]}`)                                                 |
| `rate`           | number ≥ 0            |    No    | Camera framerate (frames per second) when the message was produced                                                                  |
| `sub_detections` | array of string       |    No    | Sub-detection labels run on this frame (e.g. `["license_plate"]`)                                                                   |
| `intrinsics`     | object                |    No    | Camera intrinsic parameters (`fx`, `fy`, `cx`, `cy`); used to update camera calibration and compute image resolution                |
| `distortion`     | object                |    No    | Lens distortion coefficients keyed by name (`k1`, `k2`, `p1`, `p2`, `k3`); used alongside `intrinsics` to update camera calibration |

### Detection Object Fields (`objects.<category>[*]`)

| Field                  | Type               | Required | Description                                                                                                                                                    |
| ---------------------- | ------------------ | :------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `category`             | string             |   Yes    | Object class label (e.g. `"person"`, `"car"`)                                                                                                                  |
| `bounding_box`         | object             | One of ① | Normalized image-space bounding box (`x`, `y`, `width`, `height`)                                                                                              |
| `bounding_box_px`      | object             | One of ① | Pixel-space bounding box (`x`, `y`, `width`, `height`; optional `z`, `depth`)                                                                                  |
| `translation`          | array[3] of number | One of ① | 3D world position (`x`, `y`, `z`) in metres                                                                                                                    |
| `lat_long_alt`         | array[3] of number | One of ① | Geographic position (latitude, longitude, altitude); converted to ECEF internally                                                                              |
| `size`                 | array[3] of number | One of ① | 3D object dimensions (`x`, `y`, `z`) in metres                                                                                                                 |
| `confidence`           | number > 0         |    No    | Inference confidence score for this detection                                                                                                                  |
| `id`                   | integer ≥ 0        |  Yes ②   | Per-frame detection index                                                                                                                                      |
| `rotation`             | array[4] of number |    No    | Object orientation as a quaternion                                                                                                                             |
| `distance`             | number             |    No    | Distance from the camera to the detection in metres                                                                                                            |
| `keypoints`            | array of objects   |    No    | Pose keypoints when a pose estimation model is used; each entry: `{"name": "<keypoint>", "x": <0–1>, "y": <0–1>}` (coordinates normalized to frame dimensions) |
| `keypoint_connections` | array of strings   |    No    | Flat list of keypoint-name pairs defining connections (e.g. `["nose","eye_l","nose","eye_r",...]`); length is always `2 × number_of_connections`               |
| `metadata`             | object             |    No    | Semantic attribute bag (see [Semantic Metadata Fields](#semantic-metadata-fields))                                                                             |

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

## Sensor Input Message Format

The Scene Controller subscribes to the MQTT topic `scenescape/data/sensor/{sensor_id}` and
receives scalar sensor readings from physical or virtual sensors. Messages are validated against
the `singleton` definition in
[metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

Sensor data is used to tag tracked objects that are within the sensor's configured measurement
area. A wide variety of sensor types are supported — environmental sensors (temperature,
humidity, air quality), as well as attribute sensors such as badge readers that associate a
discrete identifier with a presence event.

### Sensor Message Fields

| Field       | Type                  | Required | Description                                                           |
| ----------- | --------------------- | :------: | --------------------------------------------------------------------- |
| `id`        | string                |   Yes    | Sensor identifier; must match the provisioned sensor ID in Scenescape |
| `timestamp` | string (ISO 8601 UTC) |   Yes    | Acquisition time of the reading                                       |
| `value`     | any                   |   Yes    | Sensor reading — numeric scalar, string, boolean, or any JSON value   |
| `subtype`   | string                |    No    | Sensor subtype hint (e.g. `"temperature"`, `"humidity"`)              |
| `rate`      | number ≥ 0            |    No    | Rate at which the sensor is producing readings (readings per second)  |

The `id` field must match the last path segment of the MQTT topic:
`scenescape/data/sensor/{sensor_id}`.

### Example Sensor Input Message

**Environmental Sensor (Temperature Reading)**

```json
{
  "id": "temperature1",
  "timestamp": "2022-09-19T21:33:09.832Z",
  "value": 22.5
}
```

Published to topic: `scenescape/data/sensor/temperature1`

The `value` field carries the scalar reading (degrees Celsius in this case). Other
environmental sensors such as humidity or air-quality monitors follow the same structure,
differing only in the `id` and the unit of the `value`.

**Other Sensor Types**

The `singleton` schema is intentionally generic — `value` is untyped and accepts any JSON
value. This makes it suitable for attribute sensors beyond simple scalars. For example:

- **Badge / access-control sensors** — `value` holds a string badge identifier (e.g.
  `"BADGE-00421"`), allowing the controller to associate a personnel ID with an object track
  inside the sensor's measurement area.
- **Boolean presence sensors** — `value` is `true`/`false` (e.g. a beam-break or pressure
  mat).
- **Light sensors** — `value` is a numeric lux reading; see
  [Controlling Scene Lighting with Physical Light Sensors](../../other-topics/light-sensor-integration.md)
  for a complete integration guide.

For a broader description of how singleton sensors work and how the tagged data appears on
scene objects, see
[Singleton Sensor Data](../../how-to-guides/integrate-cameras-and-sensors.md#singleton-sensor-data)
in the integration guide.

## External Source Input Message Format

The Scene Controller subscribes to the MQTT topic `scenescape/external/{scene_id}/{thing_type}`.
This single topic carries two message contracts, distinguished by the presence of `source_id`
in the payload:

- **Legacy configured child scene** (no `source_id`): `{scene_id}` is the _sending_ child
  scene's own ID. The controller looks up the child's configured parent scene and its static
  `cameraPose`, and transforms the child's tracked objects into the parent. This behavior is
  unchanged.
- **Unified external source** (`source_id` present): `{scene_id}` is the _target_ scene the
  source is publishing into. `source_id` identifies the publishing source (a physical agent
  such as a drone or vehicle, the Scenescape positioning service, or a child scene using the
  new contract). Messages are validated against the `external_source` definition in
  [metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

This section documents the unified external-source contract.

### External Source Top-Level Fields

| Field       | Type                  | Required | Description                                                                                                                                                                                                                                          |
| ----------- | --------------------- | :------: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timestamp` | string (ISO 8601 UTC) |   Yes    | Time the observations (and pose, if present) were acquired                                                                                                                                                                                           |
| `source_id` | string                |   Yes    | Identifier of the publishing source; combined with the topic's `{scene_id}` to key the source's pose cache                                                                                                                                           |
| `objects`   | array                 |   Yes    | Observed objects, in the source's local coordinate frame (see [External Detection Object Fields](#external-detection-object-fields-objects)); may be empty for a pose-only update                                                                    |
| `pose`      | object                |    No    | Pose of the source's local origin, used to transform `objects` into the target scene (see [External Source Pose Fields](#external-source-pose-fields-pose)); may be omitted to reuse the most recently cached, non-expired pose for this `source_id` |

### External Source Pose Fields (`pose`)

| Field                 | Type               |  Required  | Description                                                                                                           |
| --------------------- | ------------------ | :--------: | --------------------------------------------------------------------------------------------------------------------- |
| `reference_frame`     | string             |    Yes     | `"wgs84"` or `"scene"` — see below                                                                                    |
| `rotation`            | array[4] of number |    Yes     | Orientation of the source's local origin, as a quaternion (`x`, `y`, `z`, `w`)                                        |
| `lat_long_alt`        | array[3] of number | If `wgs84` | Global position of the source's local origin (latitude, longitude, altitude in metres)                                |
| `translation`         | array[3] of number | If `scene` | Position of the source's local origin in scene-local coordinates (`x`, `y`, `z`)                                      |
| `position_accuracy_m` | number > 0         |     No     | Estimated accuracy of the reported position in metres, if known                                                       |
| `provider`            | string             |     No     | Informational label for what produced this pose (e.g. `"agent"`, `"positioning_service"`); not used for authorization |

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

| Field         | Type               | Required | Description                                                                                                                                                                                                     |
| ------------- | ------------------ | :------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `category`    | string             |   Yes    | Category or class of the observed object (e.g. `"person"`, `"vehicle"`)                                                                                                                                         |
| `translation` | array[3] of number |   Yes    | Position of the object relative to the source's local origin (`x`, `y`, `z`)                                                                                                                                    |
| `id`          | string             |   Yes    | Identifier the source uses to correlate this observation across messages; not a Scenescape global ID, and the controller does not map or look it up — it is passed through as the observation's local reference |
| `rotation`    | array[4] of number |    No    | Rotation of the object as a quaternion (`x`, `y`, `z`, `w`)                                                                                                                                                     |
| `size`        | array[3] of number |    No    | Object dimensions (`x`, `y`, `z`). Omit for a point observation with no known extent                                                                                                                            |
| `confidence`  | number > 0         |    No    | Source-reported confidence for this observation                                                                                                                                                                 |
| `metadata`    | object             |    No    | Semantic attribute bag; same structure as camera input (see [Semantic Metadata Fields](#semantic-metadata-fields))                                                                                              |

Unlike camera detections, `size` is optional here: a source that cannot estimate an object's
extent may report a point observation. Point objects (no `size`) remain eligible for
position-based ROI, tripwire, and sensor-tagging analytics, but are excluded from
volume/occupancy/collision analytics.

### Pose Caching and Message Ordering

A resolved pose is cached per `(scene_id, source_id)` for `30` seconds. Subsequent messages
from the same source may omit `pose` entirely to reuse the cached transform; a message with a
`pose` and an empty `objects` array updates the cache without ingesting any observations.
Messages with a `timestamp` older than the currently cached pose are treated as out-of-order
and ignored in favor of the newer cached transform. If no usable transform can be resolved
(no pose supplied and nothing cached, or the cached pose has expired), the message is dropped
without ingesting objects. Rejection reasons (logged, not published) include:

| Reason                           | Cause                                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------------- |
| `no_pose_available`              | No `pose` supplied and no prior cached transform for this `(scene_id, source_id)`           |
| `pose_expired`                   | No `pose` supplied and the cached transform is older than the cache TTL                     |
| `scene_georeference_unavailable` | `reference_frame: wgs84` but the target scene has no valid geospatial calibration           |
| `untrusted_scene_pose`           | `reference_frame: scene` from a `source_id` not in `CONTROLLER_TRUSTED_POSITIONING_SOURCES` |
| `unsupported_reference_frame`    | `reference_frame` is not `wgs84` or `scene`                                                 |
| `invalid_pose`                   | `pose` failed schema validation or transform construction                                   |

### Trusted Identity by Default, with Collision Detection

Every external-source object's `id` (see
[External Detection Object Fields](#external-detection-object-fields-objects)) is trusted
directly as its global track identity (`gid`) by default. There is no allowlist or environment
variable to configure, and no per-source registration step: any `source_id` may publish and have
its objects' `id`s trusted immediately. This is deliberate — requiring an operator to
pre-configure which sources are safe to trust does not scale as the number of external
sources/integrations grows.

Trusting `id` directly means the object bypasses Scenescape's kinematic multi-object tracker/ReID
association entirely for that object: the source-supplied `id` becomes `gid` and stays `gid` for
as long as the source keeps reporting that same `id` in subsequent messages, exactly matching how
a UWB/RTLS tag's own permanent hardware identifier is meant to be used. If the source stops
reporting an `id`, that track ages out and is dropped after the same staleness window used for
any other track that stops receiving updates — there is no special cleanup required.

**Collision detection.** Trusting every source's `id` unconditionally would let two different
sources that happen to report the same `id` value silently merge two distinct physical objects
under one identity. To prevent that without requiring configuration, each `id` is claimed
exclusively per `(scene, category)`: only one `source_id` may hold a live claim on a given `id`
at a time. If a second source publishes the same `id` while another source's claim on it is still
live, the newly arriving, colliding object is dropped — logged as a rejection, not merged or
substituted — while any other, non-colliding objects in the same message are still ingested
normally. A claim goes stale (and can be reclaimed by a different source) after the same
identity-claim TTL used for pose-cache reuse; a source that legitimately stops publishing an
`id` and a different source later reusing that same `id` value is therefore not permanently
blocked.

**What collision detection does _not_ cover.** It only detects two _different_ sources colliding
on the same `id` at the same time. It cannot detect — and does not attempt to detect — a single
source reusing one of its _own_ previously-claimed `id`s for a genuinely different physical
object once its earlier claim has gone stale (for example, a robot restarting and reissuing small
integer track-slot numbers that a previous, now-stale claim also used). For a source with that
kind of unstable/resettable local `id` scheme, a reused `id` will be silently accepted as if it
were a continuation of the previous object's identity. See
[Choosing a `source_id`](#choosing-a-source_id-self-identification-for-agents) below for how to
avoid this by choosing a genuinely persistent, unique identifier.

**Security note:** identity is trusted based on the `source_id`/`id` values present in the
message payload, not a cryptographically verified per-device credential — Scenescape's current
MQTT authentication does not yet bind individual publishers to individual `source_id`s (see
[ADR 14](../../../adr/0014-unified-external-source-ingestion.md#future-work)). A publisher that
can reach the broker can claim any `source_id`/`id` it chooses, subject only to the collision
check above.

### Choosing a `source_id` (Self-Identification for Agents)

`source_id` is not provisioned or registered anywhere in Scenescape ahead of time — unlike a
camera or sensor `id`, which must match a scene/sensor already configured in the database, an
external source simply announces itself by choosing a `source_id` string and publishing with it.
Because every external source's `objects[*].id` is trusted as global identity by default (see
above), choosing a persistent, unique `source_id` and per-object `id` matters more here than for
most other Scenescape identifiers: the deployer/integrator is responsible for choosing values
that are:

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
   Scenescape (see the [Sensor Input Message Format](#sensor-input-message-format) example,
   `02:42:ac:11:00:05.1`).
3. **A deployer-assigned static name** (for example `"drone-1"`, `"forklift-north-3"`) — acceptable
   as long as it is provisioned once per physical device and not regenerated on every boot or
   process restart.

**Do not** use a randomly generated value (for example a fresh UUID minted at process startup)
as `source_id` or as an object's `id`: it defeats pose-cache reuse across restarts and, since
every object's `id` is trusted directly as identity, means each restart creates a brand-new
identity for what should be the same physical object. Worse, for a source whose local `id`
scheme resets or recycles (for example, small integer track-slot numbers reissued after a
reboot), a reused `id` is silently treated as a continuation of the previous object's identity
once the earlier claim has gone stale — see the collision-detection limitation above. Prefer a
hardware-rooted or MAC-based identifier specifically to avoid this.

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

A pose-only update refreshes the cached transform without ingesting observations:

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

All Scene Controller output messages include an `objects` array of tracked objects. Each
tracked object contains the following fields:

| Field                  | Type               | Description                                                                                                                                                                                                                                                  |
| ---------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`                   | string (UUID)      | Persistent track identifier assigned by the controller                                                                                                                                                                                                       |
| `type`                 | string             | Object type label; same value as `category` (e.g. `"person"`)                                                                                                                                                                                                |
| `category`             | string             | Object class label (e.g. `"person"`)                                                                                                                                                                                                                         |
| `confidence`           | number             | Inference confidence of the most recent contributing detection                                                                                                                                                                                               |
| `translation`          | array[3] of number | 3D world position (`x`, `y`, `z`) in metres                                                                                                                                                                                                                  |
| `size`                 | array[3] of number | 3D object dimensions (`x`, `y`, `z`) in metres                                                                                                                                                                                                               |
| `velocity`             | array[3] of number | Velocity vector (`x`, `y`, `z`) in metres per second                                                                                                                                                                                                         |
| `rotation`             | array[4] of number | Orientation quaternion                                                                                                                                                                                                                                       |
| `visibility`           | array of string    | Camera IDs currently observing this object                                                                                                                                                                                                                   |
| `keypoints`            | array of objects   | Pose keypoints propagated from detections when available; each entry uses `{"name": "<keypoint>", "x": <0-1>, "y": <0-1>}` coordinates normalized to frame dimensions                                                                                        |
| `keypoint_connections` | array of strings   | Flat list of keypoint-name pairs defining the skeleton edges (e.g. `["nose","eye_l","nose","eye_r",...]`); length is always `2 x number_of_connections`                                                                                                      |
| `regions`              | object             | Map of region/sensor IDs to membership metadata. By default this is `{id: {entered: timestamp}}`. In region-scoped outputs, objects currently inside a region also include a live dwell time as `{id: {entered: timestamp, dwell: seconds}}`.                |
| `sensors`              | object             | Map of sensor IDs to timestamped readings (`{id: [[timestamp, value], ...]}`)                                                                                                                                                                                |
| `similarity`           | number or null     | Similarity/distance value to the matched ReID embedding in VDMS; higher-is-better for `COSINE`; lower is better for `L2`. `null` when ReID is still collecting embeddings, when no database match was found, or when ReID is disabled.                       |
| `reid_state`           | string             | Re-ID processing state for the object. One of: `pending_collection`, `query_no_match`, `matched`, `reid_disabled`                                                                                                                                            |
| `previous_ids_chain`   | array or absent    | History of UUID reassignments for this track. Each element is `{"id": "<uuid>", "timestamp": "<ISO 8601>", "similarity_score": <number or null>}`. Present only when the object has been re-identified at least once; omitted otherwise.                     |
| `first_seen`           | string (ISO 8601)  | Timestamp when the track was first created                                                                                                                                                                                                                   |
| `metadata`             | object             | Semantic attributes propagated from camera detections; present when visual analytics (e.g. age, gender, Re-ID) are configured. Same attribute structure as camera input. See note below.                                                                     |
| `camera_bounds`        | object             | Per-camera pixel bounding boxes (`{camera_id: {x, y, width, height, projected}}`) where `projected=false` means detector-provided pixel bbox and `projected=true` means computed projection; may be empty (`{}`) when no camera currently observes the track |

> **Note on `metadata` in track objects**: Each attribute follows the structure
> `{label, model_name, confidence?}` — identical to [Semantic Metadata Fields](#semantic-metadata-fields)
> in camera input. The `reid` attribute is a special case: in scene output
> `reid.embedding_vector` is a **2D float array** (`[[...numbers...]]`), whereas in
> camera input it is a base64-encoded string. `metadata` is absent when no semantic
> analytics pipeline is configured.

> **Note on keypoint propagation**: `keypoints` and `keypoint_connections` are
> optional pass-through fields from object detections. They are included in output
> objects when present on the contributing detection data.

> **Note on `similarity`**: This field holds the metric value returned by VDMS
> in `_distance` and is evaluated by the controller using configured metric semantics.
> For `COSINE` (implemented via VDMS `IP`), value must be above `similarity_threshold`; for distance-style metrics such as `L2`,
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

> **Note on live region dwell**: In region data and region event payloads, objects that are
> still inside a region include `regions.<region_id>.dwell`, which is the current elapsed
> time in seconds since that object entered the region. Exit records continue to expose the
> final dwell time separately as `{"object": <track>, "dwell": <seconds>}` in the
> top-level `exited` array.

## Data Scene Output Message Format

Published on MQTT topic: `scenescape/data/scene/{scene_id}/{thing_type}`

The Scene Controller publishes unregulated (raw) tracking results, one message per object
category per scene publication cycle. Each message contains the current state of all tracked
objects of that category.

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
      "regions": {
        "ee94126c-1c5a-4ee0-ab5d-0819ba3fc9b4": {
          "entered": "2026-03-26T20:49:51.349Z"
        }
      },
      "sensors": {
        "temperature_1": [["2026-03-26T20:49:53.661Z", 70]]
      },
      "similarity": null,
      "reid_state": "pending_collection",
      "first_seen": "2026-03-26T20:49:49.339Z"
    }
  ]
}
```

## Regulated Scene Output Message Format

Published on MQTT topic: `scenescape/regulated/scene/{scene_id}`

The Scene Controller publishes regulated (rate-controlled) tracking results aggregating all
object categories into a single message. This is the primary output topic for downstream
applications.

### Regulated Scene Top-Level Fields

| Field        | Type                  | Description                                                                     |
| ------------ | --------------------- | ------------------------------------------------------------------------------- |
| `id`         | string                | Scene identifier (UUID)                                                         |
| `timestamp`  | string (ISO 8601 UTC) | Publication timestamp                                                           |
| `name`       | string                | Scene name                                                                      |
| `scene_rate` | number                | Regulated publication rate in Hz                                                |
| `rate`       | object                | Map of camera IDs to their current framerates (e.g. `{"cam1": 10.0}`)           |
| `objects`    | array                 | Tracked objects (see [Common Output Track Fields](#common-output-track-fields)) |

### Example Regulated Scene Message

```json
{
  "id": "302cf49a-97ec-402d-a324-c5077b280b7b",
  "timestamp": "2026-03-26T20:48:50.149Z",
  "name": "Queuing",
  "scene_rate": 38.8,
  "rate": {
    "atag-qcam1": 9.998,
    "atag-qcam2": 10.018
  },
  "objects": [
    {
      "id": "0c373dbf-2a1d-49b7-ba2d-48711d189971",
      "category": "person",
      "type": "person",
      "confidence": 0.998,
      "translation": [2.204, 3.29, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [-0.489, 0.25, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "metadata": {
        "age": { "label": "41", "model_name": "age_gender" },
        "gender": {
          "label": "Male",
          "model_name": "age_gender",
          "confidence": 0.963
        },
        "reid": {
          "embedding_vector": "<embedding_dimensions-element float array>",
          "embedding_dimensions": 256,
          "model_name": "torch-jit-export"
        }
      },
      "camera_bounds": {
        "atag-qcam2": {
          "x": 760,
          "y": 49,
          "width": 191,
          "height": 375,
          "projected": false
        }
      },
      "regions": {
        "ee94126c-1c5a-4ee0-ab5d-0819ba3fc9b4": {
          "entered": "2026-03-26T20:48:46.344Z"
        }
      },
      "sensors": {
        "temperature_1": [
          ["2026-03-26T20:48:45.629Z", 79],
          ["2026-03-26T20:48:46.630Z", 14]
        ]
      },
      "similarity": null,
      "reid_state": "pending_collection",
      "first_seen": "2026-03-26T20:48:42.857Z"
    }
  ]
}
```

## Region Event Output Message Format

Published on MQTT topic: `scenescape/event/region/{scene_id}/{region_id}/{event_type}`

The Scene Controller publishes an event when the set of tracked objects inside a region of
interest changes. The `{event_type}` segment is typically `objects`.

### Region Event Top-Level Fields

| Field         | Type                  | Description                                                                                                        |
| ------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `timestamp`   | string (ISO 8601 UTC) | Event timestamp                                                                                                    |
| `scene_id`    | string                | Scene identifier (UUID)                                                                                            |
| `scene_name`  | string                | Scene name                                                                                                         |
| `region_id`   | string                | Region identifier (UUID)                                                                                           |
| `region_name` | string                | Region name                                                                                                        |
| `counts`      | object                | Map of category to object count currently inside the region (e.g. `{"person": 2}`)                                 |
| `objects`     | array                 | Tracked objects currently inside the region (#common-output-track-fields)                                          |
| `entered`     | array                 | Objects that entered the region during this cycle; Empty when no entry occurred                                    |
| `exited`      | array                 | Objects that exited the region during this cycle; Empty when no exit occurred                                      |
| `metadata`    | object                | Region geometry: `title`, `uuid`, `points` (polygon vertices in metres), `area` (`"poly"`), `fromSensor` (boolean) |

### Example Region Event Message

```json
{
  "timestamp": "2026-03-26T20:53:32.045Z",
  "scene_id": "302cf49a-97ec-402d-a324-c5077b280b7b",
  "scene_name": "Queuing",
  "region_id": "ee94126c-1c5a-4ee0-ab5d-0819ba3fc9b4",
  "region_name": "region_2",
  "counts": {
    "person": 2
  },
  "objects": [
    {
      "id": "2d3c96d9-24bd-498b-ba1f-2fd54ab6c25b",
      "category": "person",
      "type": "person",
      "confidence": 0.999,
      "translation": [2.557, 3.678, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [-0.118, 0.186, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "camera_bounds": {
        "atag-qcam2": {
          "x": 799,
          "y": 14,
          "width": 169,
          "height": 397,
          "projected": false
        }
      },
      "sensors": {
        "temperature_1": [["2026-03-26T20:53:29.761Z", 48]]
      },
      "similarity": null,
      "first_seen": "2026-03-26T20:53:25.339Z"
    }
  ],
  "entered": [
    {
      "id": "2d3c96d9-24bd-498b-ba1f-2fd54ab6c25b",
      "category": "person",
      "type": "person",
      "confidence": 0.999,
      "translation": [2.557, 3.678, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [-0.118, 0.186, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "similarity": null,
      "first_seen": "2026-03-26T20:53:25.339Z"
    }
  ],
  "exited": [
    {
      "object": {
        "id": "bbd07321-dbb9-4384-bf1b-4eb5d9a0aa05",
        "category": "person",
        "type": "person",
        "confidence": 0.98,
        "translation": [0.893, 5.709, 0.0],
        "size": [0.5, 0.5, 1.85],
        "velocity": [0.005, -0.012, 0.0],
        "rotation": [0, 0, 0, 1],
        "visibility": ["atag-qcam2"],
        "regions": {},
        "similarity": null,
        "first_seen": "2026-03-26T20:53:06.647Z",
        "camera_bounds": {
          "atag-qcam2": {
            "x": 180,
            "y": 115,
            "width": 166,
            "height": 400,
            "projected": false
          }
        }
      },
      "dwell": 5.297
    }
  ],
  "metadata": {
    "title": "region_2",
    "uuid": "ee94126c-1c5a-4ee0-ab5d-0819ba3fc9b4",
    "points": [
      [0.77, 6.528],
      [1.286, 2.363],
      [4.961, 1.101],
      [3.394, 4.828],
      [1.923, 6.261]
    ],
    "area": "poly",
    "fromSensor": false
  }
}
```

> **Note on `entered` vs `exited` element shape**: In region events, `entered` elements
> are bare track objects, while `exited` elements are wrapped as
> `{"object": <track>, "dwell": <seconds>}` where `dwell` is the time in seconds the
> object spent inside the region.

## Tripwire Event Output Message Format

Published on MQTT topic: `scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}`

The Scene Controller publishes an event when a tracked object crosses a tripwire. The
`{event_type}` segment is typically `objects`. Each crossing object carries a `direction`
field (`1` or `-1`) indicating which side of the wire it crossed toward.

### Tripwire Event Top-Level Fields

| Field           | Type                  | Description                                                                                                                                 |
| --------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `timestamp`     | string (ISO 8601 UTC) | Event timestamp                                                                                                                             |
| `scene_id`      | string                | Scene identifier (UUID)                                                                                                                     |
| `scene_name`    | string                | Scene name                                                                                                                                  |
| `tripwire_id`   | string                | Tripwire identifier (UUID)                                                                                                                  |
| `tripwire_name` | string                | Tripwire name                                                                                                                               |
| `counts`        | object                | Map of category to crossing object count (e.g. `{"person": 1}`)                                                                             |
| `objects`       | array                 | Objects that triggered the event; each carries a `direction` field in addition to [Common Output Track Fields](#common-output-track-fields) |
| `entered`       | array                 | Always empty (`[]`) in tripwire events; crossing objects appear in `objects` with a `direction` field instead                               |
| `exited`        | array                 | Always empty (`[]`) in tripwire events                                                                                                      |
| `metadata`      | object                | Tripwire geometry: `title`, `points` (array of `[x, y]` coordinates in metres), `uuid`                                                      |

### Example Tripwire Event Message

```json
{
  "timestamp": "2026-03-26T20:51:39.241Z",
  "scene_id": "302cf49a-97ec-402d-a324-c5077b280b7b",
  "scene_name": "Queuing",
  "tripwire_id": "5fc8df22-0497-411c-9a62-90218cb20d7d",
  "tripwire_name": "tripwire_1",
  "counts": {
    "person": 1
  },
  "objects": [
    {
      "id": "d62d8bbf-9008-40f5-84f8-9faca9e03d90",
      "category": "person",
      "type": "person",
      "confidence": 0.999,
      "translation": [1.043, 3.542, 0.0],
      "size": [0.5, 0.5, 1.85],
      "velocity": [0.374, -0.824, 0.0],
      "rotation": [0, 0, 0, 1],
      "visibility": ["atag-qcam1", "atag-qcam2"],
      "camera_bounds": {
        "atag-qcam2": {
          "x": 796,
          "y": 175,
          "width": 257,
          "height": 504,
          "projected": false
        }
      },
      "similarity": null,
      "first_seen": "2026-03-26T20:51:37.336Z",
      "direction": -1
    }
  ],
  "entered": [],
  "exited": [],
  "metadata": {
    "title": "tripwire_1",
    "points": [
      [3.745, 6.082],
      [0.878, 3.573]
    ],
    "uuid": "5fc8df22-0497-411c-9a62-90218cb20d7d"
  }
}
```
