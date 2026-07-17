<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Scene Controller Data Formats

## Message Formats Overview

| Message Format                                                        | Direction | MQTT Topic                                      |
| --------------------------------------------------------------------- | --------- | ----------------------------------------------- |
| [Camera Input Message Format](#camera-input-message-format)           | Subscribe | `scenescape/data/camera/{camera_id}`            |
| [Data Scene Output Message Format](#data-scene-output-message-format) | Publish   | `scenescape/data/scene/{scene_id}/{thing_type}` |

The Scene Controller only tracks objects and publishes unregulated per-category output. Sensor
correlation, regulated (rate-controlled) output, and region/tripwire event publishing are owned
by the **Analytics** microservice — see
[Analytics Service Data Formats](../analytics/data_formats.md) for those message formats
(`scenescape/data/sensor/{sensor_id}`, `scenescape/regulated/scene/{scene_id}`,
`scenescape/event/region/{scene_id}/{region_id}/{event_type}`, `scenescape/event/tripwire/{scene_id}/{tripwire_id}/{event_type}`).

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

## Common Output Track Fields

> **Note**: Sensor input (`scenescape/data/sensor/{sensor_id}`) is no longer consumed by the
> Scene Controller. Sensor correlation is owned by the **Analytics** microservice — see
> [Sensor Input Message Format](../analytics/data_formats.md#sensor-input-message-format)
> and [Singleton Sensor Data](../../how-to-guides/integrate-cameras-and-sensors.md#singleton-sensor-data)
> for the sensor input message format and how tagged data appears on scene objects.

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
| `regions`              | object             | Map of region/sensor IDs to membership metadata. **Never populated by the Scene Controller** — added by the Analytics microservice when it enriches this data; see note below.                                                                               |
| `sensors`              | object             | Map of sensor IDs to timestamped readings (`{id: [[timestamp, value], ...]}`). **Never populated by the Scene Controller** — added by the Analytics microservice; see note below.                                                                            |
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

> **Note on `regions`/`sensors`**: These fields are added by the Analytics microservice
> when it consumes `scenescape/data/scene/{scene_id}/{thing_type}` and republishes enriched,
> regulated, and region/tripwire-event output. `regions` defaults to `{id: {entered: timestamp}}`
> and gains a live `dwell` value for objects currently inside a region:
> `{id: {entered: timestamp, dwell: seconds}}`. Exit records expose the final dwell time
> separately as `{"object": <track>, "dwell": <seconds>}` in the top-level `exited` array.
> See [Regulated Scene Output Message Format](../analytics/data_formats.md#regulated-scene-output-message-format)
> for full format details.

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
