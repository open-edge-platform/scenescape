<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Camera Detection Metadata Format

Input metadata received via MQTT on `data/camera/<camera-id>` topics from visual analytics pipelines. The schema definition is `detector` inside `metadata.schema.json`. Sample data is in `data/data_camera*.json`.

---

## Top-Level Message Fields

| JSON Path | Schema Type | Schema Required | In `data_camera.json` | In `data_camera_2.json` | Notes |
|-----------|-------------|:---:|-----------------------|-------------------------|-------|
| `$.id` | `string` | Yes | `"camera1"` | `"atag-qcam1"` | Camera / sensor ID |
| `$.timestamp` | `string` (ISO 8601) | Yes | ✓ | ✓ | UTC acquisition time |
| `$.objects` | `object` | Yes | ✓ | ✓ | Category-keyed object map |
| `$.sub_detections` | `array<string>` | No | — | — | Optional sub-detection labels |
| `$.rate` | `number ≥ 0` | **Not defined** | `9.79` | `10.03` | Valid per `additionalProperties: true`; not in `detector` definition |
| `$.debug_mac` | — | **Not defined** | `"21:a9:85:..."` | `"27:ac:97:..."` | Debug field; not in schema |
| `$.debug_timestamp_end` | — | **Not defined** | ✓ | ✓ | Debug field; not in schema |
| `$.debug_processing_time` | — | **Not defined** | ✓ | ✓ | Debug field; not in schema |

---

## Detection Object Fields (`$.objects.<category>[*]`)

| JSON Path (relative to detection) | Schema Type | Schema Required | In `data_camera.json` | In `data_camera_2.json` | Notes |
|-----------------------------------|-------------|:---:|-----------------------|-------------------------|-------|
| `.category` | `string` | Yes | `"person"` | `"person"` | Object class label |
| `.confidence` | `number > 0` | No | `0.813` | `0.998` | Inference confidence |
| `.id` | `integer ≥ 0` | No | `1` | `1`, `2` | Per-frame detection index |
| `.bounding_box` | `object` | One of ① | — | — | Normalized coords; unused in samples |
| `.bounding_box.x` | `number` | If `.bounding_box` | — | — | Top-left x (0–1 normalized) |
| `.bounding_box.y` | `number` | If `.bounding_box` | — | — | Top-left y (0–1 normalized) |
| `.bounding_box.width` | `number ≥ 0` | If `.bounding_box` | — | — | Width (normalized) |
| `.bounding_box.height` | `number ≥ 0` | If `.bounding_box` | — | — | Height (normalized) |
| `.bounding_box_px` | `object` | One of ① | ✓ | ✓ | Pixel-space bounding box |
| `.bounding_box_px.x` | `number` | If `.bounding_box_px` | `169` | `419` | Top-left x (pixels) |
| `.bounding_box_px.y` | `number` | If `.bounding_box_px` | `4` | `64` | Top-left y (pixels) |
| `.bounding_box_px.width` | `number ≥ 0` | If `.bounding_box_px` | `96` | `192` | Width (pixels) |
| `.bounding_box_px.height` | `number ≥ 0` | If `.bounding_box_px` | `168` | `411` | Height (pixels) |
| `.bounding_box_px.z` | `number` | No | — | — | Optional; unused in samples |
| `.bounding_box_px.depth` | `number ≥ 0` | No | — | — | Optional; unused in samples |
| `.translation` | `array[3]<number>` | One of ① | — | — | 3-D position (x, y, z); used in scene output, not camera input |
| `.size` | `array[3]<number > 0>` | One of ① | — | — | 3-D size (x, y, z); used in scene output, not camera input |
| `.rotation` | `array[4]<number>` | No | — | — | Quaternion; unused in samples |
| `.center_of_mass` | `object` | No | ✓ | ✓ | Depth-estimation ROI (pixels) |
| `.center_of_mass.x` | `number` | If `.center_of_mass` | `201` | `482` | Pixels from left |
| `.center_of_mass.y` | `number` | If `.center_of_mass` | `46` | `165` | Pixels from top |
| `.center_of_mass.width` | `number ≥ 0` | If `.center_of_mass` | `32` | `64` | Width (pixels) |
| `.center_of_mass.height` | `number ≥ 0` | If `.center_of_mass` | `42` | `102.75` | Height (pixels) |
| `.distance` | `number` | No | — | — | Distance to object in metres; unused in samples |
| `.metadata` | `object` | No | — | ✓ | Semantic attribute bag |

> ① **`detection` `oneOf` constraint** — every detection must contain exactly one of:
> - `bounding_box` (normalized), OR `bounding_box_px` (pixels)
> - `translation` + `size` (3-D world coords)
> - `lat_long_alt` + `size` (geo coords)

---

## Semantic Metadata Fields (`$.objects.<category>[*].metadata.<attr>`)

| JSON Path (relative to `.metadata`) | Schema Type | Schema Required | In `data_camera_2.json` example | Notes |
|-------------------------------------|-------------|:---:|----------------------------------|-------|
| `.<attr>.label` | any | Yes | `"39"` (age), `"Male"` (gender) | Detected value |
| `.<attr>.model_name` | `string` | Yes | `"age_gender"` | Source model identifier |
| `.<attr>.confidence` | `number` [0, 1] | No | `0.979` (gender), absent (age) | Optional per attribute |
| `.reid.embedding_vector` | `string` | Yes (for reid) | base64 string | ReID embedding; special case in schema |
| `.reid.model_name` | `string` | Yes (for reid) | `"torch-jit-export"` | Source model identifier |

---

## Schema vs. Sample Data: Differences Summary

| # | JSON Path | Issue | Severity | Detail |
|---|-----------|-------|:--------:|--------|
| 1 | `$.rate` | Field present in both samples but **not declared** in `detector` definition | Low | Defined only in `singleton`; passes validation via `additionalProperties: true` |
| 2 | `$.debug_mac` | Present in samples; **absent from schema** | Low | Debug field; matches `mac` definition pattern but prefixed `debug_`; passes as additional property |
| 3 | `$.debug_timestamp_end` | Present in samples; **absent from schema** | Low | Debug field; ISO 8601 timestamp; passes as additional property |
| 4 | `$.debug_processing_time` | Present in samples; **absent from schema** | Low | Debug float (seconds); passes as additional property |
| 5 | `$.objects.<category>[*].bounding_box` | **Never used** in samples | Info | Normalized variant not demonstrated; samples exclusively use `bounding_box_px` |
| 6 | `$.objects.<category>[*].bounding_box_px.z` / `.depth` | **Never used** in samples | Info | 3-D bounding box optional fields; not populated by camera pipelines |
| 7 | `$.objects.<category>[*].translation`, `.size`, `.rotation` | **Never used** in samples | Info | World-space fields; populated by the controller in scene output, not camera input |
| 8 | `$.objects.<category>[*].distance` | **Never used** in samples | Info | Optional; populated only with depth-capable sensors (e.g., RealSense / LiDAR) |
| 9 | `$.sub_detections` | **Never used** in samples | Info | Optional; populated when nested detection pipelines run (e.g., license-plate inside vehicle) |
| 10 | `$.objects.<category>[*].metadata.<attr>.confidence` | **Absent for `age` attribute** in sample | Info | Schema marks `confidence` optional; `age` entry omits it, which is valid |

All differences are **schema-valid** (no violations). The debug fields (`debug_mac`, `debug_timestamp_end`, `debug_processing_time`) and `rate` are extra operational fields not formalized in the `detector` definition.

---

## Controller Use of Extra (Non-Schema) Fields

### Fields read from the incoming camera message

| JSON Path | Accessed in | Access pattern | Purpose |
|-----------|-------------|----------------|---------|
| `$.rate` | `scene_controller.py:223` | `jdata.get('rate', None)` | Stored per-camera in the regulated publish cache to track each contributing camera's framerate |
| `$.rate` | `scene_controller.py:229` | `jdata['rate']` | In analytics-only mode, the single rate value is spread to all cameras listed in each object's `visibility` array |
| `$.intrinsics` | `cache_manager.py:108,114` | `jdata.get('intrinsics', {})` | Extracts `cx`/`cy` to compute image resolution; calls `updateCamera()` to push calibration to the scene; triggers full scene refresh if changed |
| `$.distortion` | `cache_manager.py:109` | `jdata.get('distortion', ...)` | Same mechanism as `intrinsics`; triggers a scene refresh when changed |
| `$.updatecamera` | `scene_controller.py:435` | presence check (`'updatecamera' in jdata`) | **Control signal**: if this field is present the entire detector message is discarded immediately (early `return`) |

### Fields injected by the controller before forwarding to scene topics

| JSON Path | Injected in | Description |
|-----------|-------------|-------------|
| `$.debug_hmo_start_time` | `scene_controller.py:438` | Set to current epoch time when the MQTT handler begins processing the message |
| `$.debug_hmo_processing_time` | `scene_controller.py:189` | Computed as `now − debug_hmo_start_time`; written just before publishing to the scene topic |

### Camera pipeline `debug_*` fields — not used by the controller

| JSON Path | Status |
|-----------|--------|
| `$.debug_mac` | Ignored — not accessed anywhere in the controller |
| `$.debug_timestamp_end` | Ignored — not accessed anywhere in the controller |
| `$.debug_processing_time` | Ignored — not accessed anywhere in the controller |

`rate`, `intrinsics`, and `distortion` are the only non-schema fields the controller meaningfully depends on. `updatecamera` is a control-plane escape hatch. The `debug_*` fields emitted by camera pipelines are pass-through noise — they are forwarded in the JSON blob but never read by the controller.
