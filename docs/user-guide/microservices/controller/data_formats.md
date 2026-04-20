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

| Field             | Type               | Required | Description                                                                        |
| ----------------- | ------------------ | :------: | ---------------------------------------------------------------------------------- |
| `category`        | string             |   Yes    | Object class label (e.g. `"person"`, `"car"`)                                      |
| `bounding_box`    | object             | One of ① | Normalized image-space bounding box (`x`, `y`, `width`, `height`)                  |
| `bounding_box_px` | object             | One of ① | Pixel-space bounding box (`x`, `y`, `width`, `height`; optional `z`, `depth`)      |
| `translation`     | array[3] of number | One of ① | 3D world position (`x`, `y`, `z`) in metres                                        |
| `lat_long_alt`    | array[3] of number | One of ① | Geographic position (latitude, longitude, altitude); converted to ECEF internally  |
| `size`            | array[3] of number | One of ① | 3D object dimensions (`x`, `y`, `z`) in metres                                     |
| `confidence`      | number > 0         |    No    | Inference confidence score for this detection                                      |
| `id`              | integer ≥ 0        |  Yes ②   | Per-frame detection index                                                          |
| `rotation`        | array[4] of number |    No    | Object orientation as a quaternion                                                 |
| `distance`        | number             |    No    | Distance from the camera to the detection in metres                                |
| `metadata`        | object             |    No    | Semantic attribute bag (see [Semantic Metadata Fields](#semantic-metadata-fields)) |

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

| Field       | Type                  | Required | Description                                                                  |
| ----------- | --------------------- | :------: | ---------------------------------------------------------------------------- |
| `id`        | string                |   Yes    | Sensor identifier; must match the provisioned sensor ID in Intel® SceneScape |
| `timestamp` | string (ISO 8601 UTC) |   Yes    | Acquisition time of the reading                                              |
| `value`     | any                   |   Yes    | Sensor reading — numeric scalar, string, boolean, or any JSON value          |
| `subtype`   | string                |    No    | Sensor subtype hint (e.g. `"temperature"`, `"humidity"`)                     |
| `rate`      | number ≥ 0            |    No    | Rate at which the sensor is producing readings (readings per second)         |

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

## Common Output Track Fields

All Scene Controller output messages include an `objects` array of tracked objects. Each
tracked object contains the following fields:

| Field           | Type               | Description                                                                                                                                                                                                                                                  |
| --------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`            | string (UUID)      | Persistent track identifier assigned by the controller                                                                                                                                                                                                       |
| `type`          | string             | Object type label; same value as `category` (e.g. `"person"`)                                                                                                                                                                                                |
| `category`      | string             | Object class label (e.g. `"person"`)                                                                                                                                                                                                                         |
| `confidence`    | number             | Inference confidence of the most recent contributing detection                                                                                                                                                                                               |
| `translation`   | array[3] of number | 3D world position (`x`, `y`, `z`) in metres                                                                                                                                                                                                                  |
| `size`          | array[3] of number | 3D object dimensions (`x`, `y`, `z`) in metres                                                                                                                                                                                                               |
| `velocity`      | array[3] of number | Velocity vector (`x`, `y`, `z`) in metres per second                                                                                                                                                                                                         |
| `rotation`      | array[4] of number | Orientation quaternion                                                                                                                                                                                                                                       |
| `visibility`    | array of string    | Camera IDs currently observing this object                                                                                                                                                                                                                   |
| `regions`       | object             | Map of region/sensor IDs to entry timestamps (`{id: {entered: timestamp}}`)                                                                                                                                                                                  |
| `sensors`       | object             | Map of sensor IDs to timestamped readings (`{id: [[timestamp, value], ...]}`)                                                                                                                                                                                |
| `similarity`    | number or null     | Re-ID similarity score; `null` when not computed                                                                                                                                                                                                             |
| `first_seen`    | string (ISO 8601)  | Timestamp when the track was first created                                                                                                                                                                                                                   |
| `metadata`      | object             | Semantic attributes propagated from camera detections; present when visual analytics (e.g. age, gender, Re-ID) are configured. Same attribute structure as camera input. See note below.                                                                     |
| `camera_bounds` | object             | Per-camera pixel bounding boxes (`{camera_id: {x, y, width, height, projected}}`) where `projected=false` means detector-provided pixel bbox and `projected=true` means computed projection; may be empty (`{}`) when no camera currently observes the track |

> **Note on `metadata` in track objects**: Each attribute follows the structure
> `{label, model_name, confidence?}` — identical to [Semantic Metadata Fields](#semantic-metadata-fields)
> in camera input. The `reid` attribute is a special case: in scene output
> `reid.embedding_vector` is a **2D float array** (`[[...numbers...]]`), whereas in
> camera input it is a base64-encoded string. `metadata` is absent when no semantic
> analytics pipeline is configured.

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
          "embedding_vector": "<256-element float array>",
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
          "embedding_vector": "<256-element float array>",
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

| Field         | Type                  | Description                                                                                                                              |
| ------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `timestamp`   | string (ISO 8601 UTC) | Event timestamp                                                                                                                          |
| `scene_id`    | string                | Scene identifier (UUID)                                                                                                                  |
| `scene_name`  | string                | Scene name                                                                                                                               |
| `region_id`   | string                | Region identifier (UUID)                                                                                                                 |
| `region_name` | string                | Region name                                                                                                                              |
| `counts`      | object                | Map of category to object count currently inside the region (e.g. `{"person": 2}`)                                                       |
| `objects`     | array                 | Tracked objects currently inside the region (see [Common Output Track Fields](#common-output-track-fields))                              |
| `entered`     | array                 | Objects that entered the region during this cycle; each element is a bare track object. Empty when no entry occurred                     |
| `exited`      | array                 | Objects that exited the region during this cycle; each element is `{"object": <track>, "dwell": <seconds>}`. Empty when no exit occurred |
| `metadata`    | object                | Region geometry: `title`, `uuid`, `points` (polygon vertices in metres), `area` (`"poly"`), `fromSensor` (boolean)                       |

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
