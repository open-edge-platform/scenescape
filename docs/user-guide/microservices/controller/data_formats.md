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
