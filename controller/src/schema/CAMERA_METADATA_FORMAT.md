<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Camera Detection Metadata Format

Input metadata received via MQTT on `data/camera/<camera-id>` topics from visual analytics pipelines. The schema definition is `detector` inside `metadata.schema.json`. Sample data is in `data/data_camera*.json`.

---

## Top-Level Message Fields

| JSON Path | Schema Type | Schema Required | In `data_camera.json` | In `data_camera_2.json` | In `data_camera_sub-objects.json` | Notes |
|-----------|-------------|:---:|-----------------------|-------------------------|-----------------------------------|-------|
| `$.id` | `string` | Yes | `"camera1"` | `"atag-qcam1"` | `"atag-qcam1"` | Camera / sensor ID |
| `$.timestamp` | `string` (ISO 8601) | Yes | ✓ | ✓ | ✓ | UTC acquisition time |
| `$.objects` | `object` | Yes | ✓ | ✓ | ✓ | Category-keyed object map |
| `$.sub_detections` | `array<string>` | No | — | — | — | Optional top-level sub-detection labels |
| `$.rate` | `number ≥ 0` | **Not defined** | `9.79` | `10.03` | `10.68` | Valid per `additionalProperties: true`; not in `detector` definition |
| `$.debug_mac` | — | **Not defined** | `"21:a9:85:..."` | `"27:ac:97:..."` | `"b9:15:07:..."` | Debug field; not in schema |
| `$.debug_timestamp_end` | — | **Not defined** | ✓ | ✓ | ✓ | Debug field; not in schema |
| `$.debug_processing_time` | — | **Not defined** | ✓ | ✓ | ✓ | Debug field; not in schema |

---

## Detection Object Fields (`$.objects.<category>[*]`)

| JSON Path (relative to detection) | Schema Type | Schema Required | In `data_camera.json` | In `data_camera_2.json` | In `data_camera_sub-objects.json` | Notes |
|-----------------------------------|-------------|:---:|-----------------------|-------------------------|-----------------------------------|-------|
| `.category` | `string` | Yes | `"person"` | `"person"` | `"person"` | Object class label |
| `.confidence` | `number > 0` | No | `0.813` | `0.998` | `0.988` | Inference confidence |
| `.id` | `integer ≥ 0` | No | `1` | `1`, `2` | `1` | Per-frame detection index |
| `.bounding_box` | `object` | One of ① | — | — | — | Normalized coords; unused in samples |
| `.bounding_box.x` | `number` | If `.bounding_box` | — | — | — | Top-left x (0–1 normalized) |
| `.bounding_box.y` | `number` | If `.bounding_box` | — | — | — | Top-left y (0–1 normalized) |
| `.bounding_box.width` | `number ≥ 0` | If `.bounding_box` | — | — | — | Width (normalized) |
| `.bounding_box.height` | `number ≥ 0` | If `.bounding_box` | — | — | — | Height (normalized) |
| `.bounding_box_px` | `object` | One of ① | ✓ | ✓ | ✓ | Pixel-space bounding box |
| `.bounding_box_px.x` | `number` | If `.bounding_box_px` | `169` | `419` | `503` | Top-left x (pixels) |
| `.bounding_box_px.y` | `number` | If `.bounding_box_px` | `4` | `64` | `5` | Top-left y (pixels) |
| `.bounding_box_px.width` | `number ≥ 0` | If `.bounding_box_px` | `96` | `192` | `201` | Width (pixels) |
| `.bounding_box_px.height` | `number ≥ 0` | If `.bounding_box_px` | `168` | `411` | `325` | Height (pixels) |
| `.bounding_box_px.z` | `number` | No | — | — | — | Optional; unused in samples |
| `.bounding_box_px.depth` | `number ≥ 0` | No | — | — | — | Optional; unused in samples |
| `.translation` | `array[3]<number>` | One of ① | — | — | — | 3-D position (x, y, z); used in scene output, not camera input |
| `.size` | `array[3]<number > 0>` | One of ① | — | — | — | 3-D size (x, y, z); used in scene output, not camera input |
| `.rotation` | `array[4]<number>` | No | — | — | — | Quaternion; unused in samples |
| `.center_of_mass` | `object` | No | ✓ | ✓ | ✓ | Depth-estimation ROI (pixels) |
| `.center_of_mass.x` | `number` | If `.center_of_mass` | `201` | `482` | `569` | Pixels from left |
| `.center_of_mass.y` | `number` | If `.center_of_mass` | `46` | `165` | `85` | Pixels from top |
| `.center_of_mass.width` | `number ≥ 0` | If `.center_of_mass` | `32` | `64` | `67.33` | Width (pixels) |
| `.center_of_mass.height` | `number ≥ 0` | If `.center_of_mass` | `42` | `102.75` | `81.25` | Height (pixels) |
| `.distance` | `number` | No | — | — | — | Distance to object in metres; unused in samples |
| `.metadata` | `object` | No | — | ✓ | ✓ | Semantic attribute bag |
| `.sub_objects` | `object` | **Not defined** | — | — | ✓ | Nested category-keyed detection map; not in schema; passes via `additionalProperties: true` on `detection` |

> ① **`detection` `oneOf` constraint** — every detection must contain exactly one of:
> - `bounding_box` (normalized), OR `bounding_box_px` (pixels)
> - `translation` + `size` (3-D world coords)
> - `lat_long_alt` + `size` (geo coords)

---

## Sub-Object Detection Fields (`$.objects.<category>[*].sub_objects.<sub-category>[*]`)

Present only in `data_camera_sub-objects.json`. Each detection may carry a `sub_objects` map with the same structure as the top-level `objects` map — category keys pointing to arrays of nested detection objects. The field is **not defined in the schema** but passes validation via `additionalProperties: true` on the `detection` definition.

| JSON Path (relative to `.sub_objects`) | Schema Type | In `data_camera_sub-objects.json` | Notes |
|----------------------------------------|-------------|:---------------------------------:|-------|
| `.<sub-category>` | `array` | `"face": [...]` | Same category-keyed array pattern as top-level `objects` |
| `.<sub-category>[*].category` | `string` | `"face"` | Sub-object class label |
| `.<sub-category>[*].confidence` | `number > 0` | `0.515` | Inference confidence for the sub-detection |
| `.<sub-category>[*].id` | `integer ≥ 0` | `1` | Per-frame sub-detection index |
| `.<sub-category>[*].bounding_box_px` | `object` | ✓ (`x:510, y:40, w:141, h:187`) | Pixel-space bounding box of the sub-object |
| `.<sub-category>[*].center_of_mass` | `object` | ✓ (`x:557, y:86, w:47, h:46.75`) | Depth-estimation ROI for the sub-object |
| `.<sub-category>[*].metadata` | `object` | ✓ (reid) | Semantic attribute bag; same structure as parent detection |

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
| 11 | `$.objects.<category>[*].sub_objects` | Present in `data_camera_sub-objects.json`; **absent from schema** | Low | Nested category-keyed detection map mirroring the top-level `objects` structure; passes validation via `additionalProperties: true` on `detection` |

All differences are **schema-valid** (no violations). The debug fields (`debug_mac`, `debug_timestamp_end`, `debug_processing_time`), `rate`, and `sub_objects` are extra operational fields not formalized in the `detector` definition.

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

---

## References in User Documentation

The table below catalogues every passage in the `docs/` folder that references camera detection metadata or contains JSON examples of the camera message format. For each entry the schema compliance and consistency with the camera data samples (`data_camera*.json`) are assessed.

**Schema compliance** — does the example / description agree with `metadata.schema.json` (`detector` definition)?
**Sample compliance** — does the example match the field set and conventions used in `data_camera*.json`?

| Document | Lines | Schema compliance | Sample compliance | Context of mention |
|----------|-------|:-----------------:|:-----------------:|-------------------|
| [user-guide/using-intel-scenescape/how-to-integrate-cameras-and-sensors.md](../../../docs/user-guide/using-intel-scenescape/how-to-integrate-cameras-and-sensors.md) | 95–130 | ✓ Valid | Partial | 2D detection example using normalized `bounding_box` (schema-valid `oneOf` alternative). Samples use `bounding_box_px` (pixel space) instead; this example demonstrates the other valid variant. |
| [user-guide/using-intel-scenescape/how-to-integrate-cameras-and-sensors.md](../../../docs/user-guide/using-intel-scenescape/how-to-integrate-cameras-and-sensors.md) | 133–185 | ✓ Valid | No | 3D detection example with `translation`, `rotation`, `size`, and `bounding_box` (3D x/y/z). Uses schema-valid `oneOf` path (`translation` + `size`). Samples carry no 3D fields (camera pipelines emit 2D). Note on line 182 acknowledges needing `bounding_box` alongside `translation`/`size`. |
| [user-guide/using-intel-scenescape/how-to-integrate-cameras-and-sensors.md](../../../docs/user-guide/using-intel-scenescape/how-to-integrate-cameras-and-sensors.md) | 195–223 | Partial | Partial | "Detection Metadata" example adds a `hat: { confidence, value }` attribute. Schema requires `label` + `model_name` on every semantic attribute; the example uses `value` instead of `label` and omits `model_name` — **non-compliant with `semantic_metadata_attribute`**. Line 223 links to `metadata.schema.json` for validation. |
| [user-guide/additional-resources/convert-object-detections-to-normalized-image-space.md](../../../docs/user-guide/additional-resources/convert-object-detections-to-normalized-image-space.md) | 53–67 | ✗ Non-compliant | No | Pixel-space bounding box example uses `type` (not `category`) and `bounding_box` keys `top`/`left`/`width`/`height`. Schema requires `category` and uses `x`/`y`/`width`/`height`. The format is described as a generic incoming pipeline format before conversion, not the SceneScape wire format. |
| [user-guide/additional-resources/convert-object-detections-to-normalized-image-space.md](../../../docs/user-guide/additional-resources/convert-object-detections-to-normalized-image-space.md) | 72–87 | ✓ Valid | Partial | Normalized `bounding_box` output example (after conversion). Uses `type` instead of `category` and no `id`/`timestamp` — minimal but structurally valid for showing the coordinate result. Samples use `bounding_box_px` (pixel space). |
| [design/tracker-service.md](../../../docs/design/tracker-service.md) | 78 | ✓ Valid | ✓ Matches | MQTT topic table lists `scenescape/data/camera/+`; states detections carry "bounding boxes in pixel coordinates" — consistent with samples. |
| [design/tracker-service.md](../../../docs/design/tracker-service.md) | 84–98 | ✓ Valid | ✓ Matches | Full detection message example with `id`, `timestamp`, `objects` (category-keyed map), `bounding_box_px`. Field names, types, and structure match both schema and samples. References a `camera-data.schema.json` in the tracker folder. |
| [user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md](../../../docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) | 133–136 | ✓ Valid | ✓ Matches | Documents `intrinsics` (fx, fy, cx, cy) and `distortion` (k1, k2, k3, p1, p2) fields passed in the camera message. Consistent with controller's use of these fields (`cache_manager.py`). |
| [user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md](../../../docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) | 254 | ✓ Valid | ✓ Matches | States that `PostInferenceDataPublish` publishes "in Intel® SceneScape detection format as described in `metadata.schema.json`". Correct reference. |
| [user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md](../../../docs/user-guide/other-topics/how-to-configure-dlstreamer-video-pipeline.md) | 330–340 | ✓ Valid | ✓ Matches | JSON config schema for DL Streamer: `intrinsics` array and `detection_labels` filter. Matches fields observed in samples and controller code. |
| [user-guide/microservices/controller/_assets/scene-controller-api.yaml](../../../docs/user-guide/microservices/controller/_assets/scene-controller-api.yaml) | 22–62 | Partial | Partial | AsyncAPI spec for `scenescape/data/camera/{camera_id}`. Correctly documents `timestamp`, `debug_timestamp_end`, `debug_mac`, `id`, `objects`, `intrinsics`, `distortion`. Issues: `rate` typed as `string` (schema/samples use `number`); `objects` typed as `array` (schema/samples use an `object`/map keyed by category); `frame_rate` field listed has no counterpart in schema or samples. |
| [design/vision-pipeline-overview.md](../../../docs/design/vision-pipeline-overview.md) | 58–78 | ✓ Valid | ✓ Matches | High-level description of MQTT metadata publishing from camera pipelines to SceneScape. No JSON example; description is consistent with schema and samples. |
| [design/vision-pipeline-overview.md](../../../docs/design/vision-pipeline-overview.md) | 106, 160–163 | ✓ Valid | ✓ Matches | Architecture diagram and text describe `intrinsics`/`distortion` as calibration data passed in the camera message and used for dynamically adjusting camera parameters. Consistent with controller behavior. |

---

## Data-Correctness Issues in `scene-controller-api.yaml`

The AsyncAPI spec at [user-guide/microservices/controller/_assets/scene-controller-api.yaml](../../../docs/user-guide/microservices/controller/_assets/scene-controller-api.yaml) (currently `asyncapi: "2.6.0"`) contains the following field-level errors that are independent of spec version and must be fixed regardless of whether the file is migrated to 3.0.0.

| # | Channel / field | Current declaration | Correct declaration | Source of truth | Impact |
|---|-----------------|--------------------|--------------------|-----------------|--------|
| 1 | `scenescape/data/camera/{camera_id}` → `$.objects` | `type: array` | `type: object` with `additionalProperties: { type: array, items: { type: object } }` | `metadata.schema.json` `detector.objects`; `data_camera*.json` samples | A validator would accept any array; the actual message is a category-keyed map (e.g. `{"person": [...]}`) |
| 2 | `scenescape/data/camera/{camera_id}` → `$.rate` | `type: string` | `type: number, minimum: 0` | `metadata.schema.json` `rate` definition; samples show float (e.g. `10.03`) | Type mismatch — code-generated clients would treat rate as a string |
| 3 | `scenescape/data/camera/{camera_id}` → `$.intrinsics` | `type: array, items: { type: array }` | `type: object` with properties `fx`, `fy`, `cx`, `cy` (`type: number`) | `cache_manager.py` accesses `intrinsics.get('cx')`, `intrinsics.get('cy')` | Declared as array-of-arrays; actually an object with named keys |
| 4 | `scenescape/data/camera/{camera_id}` → `$.distortion` | `type: array, items: { type: array }` | `type: array, items: { type: number }` | DL Streamer config docs (L133–136): coefficients `[k1, k2, k3, p1, p2]` | Declared as array-of-arrays; actually a flat array of numbers |
| 5 | `scenescape/data/camera/{camera_id}` → `$.frame_rate` | `type: string` (present) | — (remove) | Absent from `metadata.schema.json`, all samples, and controller source | Undocumented field with no backing definition; misleading to API consumers |
| 6 | `scenescape/regulated/scene/{scene_id}` → `$.scene_rate` | `type: float` | `type: number, minimum: 0` | JSON Schema does not define a `float` type; valid types are `number`, `integer`, `string`, `boolean`, `array`, `object`, `null` | Invalid JSON Schema type; any strict validator will reject the spec |
| 7 | `scenescape/regulated/scene/{scene_id}` → `$.rate` | `type: string` | `type: number, minimum: 0` | Same as issue #2 — camera framerate echoed into regulated scene output | Type mismatch |
