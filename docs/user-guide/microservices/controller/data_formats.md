<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# SceneScape Controller Data Formats

## Camera Input Message Format

The Scene Controller subscribes to the MQTT topic `scenescape/data/camera/{camera_id}` and
receives camera detection metadata from visual analytics pipelines. Messages are validated
against the `detector` definition in
[metadata.schema.json](https://github.com/open-edge-platform/scenescape/blob/main/controller/src/schema/metadata.schema.json).

### Top-Level Message Fields

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `id` | string | Yes | Camera or sensor identifier |
| `timestamp` | string (ISO 8601 UTC) | Yes | Acquisition time of the frame |
| `objects` | object | Yes | Category-keyed map; each value is an array of detections (e.g. `{"person": [...]}`) |
| `rate` | number ≥ 0 | No | Camera framerate (frames per second) when the message was produced |
| `sub_detections` | array of string | No | Sub-detection labels run on this frame (e.g. `["license_plate"]`) |

### Detection Object Fields (`objects.<category>[*]`)

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `category` | string | Yes | Object class label (e.g. `"person"`, `"car"`) |
| `bounding_box` | object | One of ① | Normalized image-space bounding box (`x`, `y`, `width`, `height`) |
| `bounding_box_px` | object | One of ① | Pixel-space bounding box (`x`, `y`, `width`, `height`; optional `z`, `depth`) |
| `translation` | array[3] of number | One of ① | 3D world position (`x`, `y`, `z`) in metres |
| `size` | array[3] of number | One of ① | 3D object dimensions (`x`, `y`, `z`) in metres |
| `confidence` | number > 0 | No | Inference confidence score for this detection |
| `id` | integer ≥ 0 | No | Per-frame detection index |
| `rotation` | array[4] of number | No | Object orientation as a quaternion |
| `center_of_mass` | object | No | Depth-estimation region of interest in pixels (`x`, `y`, `width`, `height`) |
| `distance` | number | No | Distance from the camera to the detection in metres |
| `metadata` | object | No | Semantic attribute bag (see [Semantic Metadata Fields](#semantic-metadata-fields)) |

> **① One-of constraint**: every detection must contain exactly one of:
> `bounding_box` **or** `bounding_box_px` (2D image-based detection), **or** both `translation` and `size` (3D world-space detection).

### Semantic Metadata Fields (`objects.<category>[*].metadata.<attr>`)

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `label` | any | Yes | Detected value for this attribute (e.g. `"Male"` for gender, `true` for a boolean) |
| `model_name` | string | Yes | Name of the model that produced this attribute |
| `confidence` | number [0, 1] | No | Confidence score for the detected attribute |

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
        "center_of_mass": {
          "x": 482,
          "y": 165,
          "width": 64,
          "height": 102.75
        },
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

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `id` | string | Yes | Sensor identifier; must match the provisioned sensor ID in Intel® SceneScape |
| `timestamp` | string (ISO 8601 UTC) | Yes | Acquisition time of the reading |
| `value` | any | Yes | Sensor reading — numeric scalar, string, boolean, or any JSON value |
| `subtype` | string | No | Sensor subtype hint (e.g. `"temperature"`, `"humidity"`) |
| `rate` | number ≥ 0 | No | Rate at which the sensor is producing readings (readings per second) |

The `id` field must match the last path segment of the MQTT topic:
`scenescape/data/sensor/{sensor_id}`.

### Example: Environmental Sensor (Temperature)

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

### Other Sensor Types

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
[Singleton Sensor Data](../../using-intel-scenescape/how-to-integrate-cameras-and-sensors.md#singleton-sensor-data)
in the integration guide.
