<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI — hard contracts (freeze)

Stable DOM ids, `window` APIs, and postMessage types that UI tests and
hybrid bridges depend on. Change only with matching test updates in the
same PR.

## Scene detail — map host

| Id / selector | Role |
| --- | --- |
| `#ss-map-host` | Map parking / adopt root |
| `#map` | Map image container |
| `#svgout` | Visible map SVG (React when `ssUseReactMap`; else Snap). Snap keeps `#svgout-snap` while React owns the contract id. |
| `#scale` | Meters-per-pixel (or px-per-m) scale |
| `#scene` | Scene id / metadata |
| `#fullscreen` | Fullscreen control |
| `#show-trails` | Trail toggle |
| `#coloring-switch` | ROI occupancy coloring |
| `#id_rois` | Hidden ROI JSON (bridge → REST) |
| `#tripwires` | Hidden tripwire JSON |
| `#id_child_rois`, `#child_tripwires`, `#child_sensors` | Child overlay JSON |

## Scene detail — toolbar / tabs

| Id | Role |
| --- | --- |
| `#new-roi`, `#save-rois`, `#empty-new-roi` | Regions toolbar |
| `#new-tripwire`, `#save-trips`, `#empty-new-tripwire` | Tripwires toolbar |
| `#live-view`, `#show-telemetry` | Live / telemetry |
| `#regions-tab`, `#tripwires-tab`, `#cameras-tab`, `#sensors-tab`, `#children-tab` | Tabs |
| `#regions`, `#trips` | Tab panes |
| `#roi-fields`, `#tripwire-fields` | Editor card mounts |
| `#no-regions`, `#no-tripwires` | Empty states |
| `#mqtt_status`, `#broker` | MQTT panel |

## ROI / tripwire editor cards

| Pattern | Role |
| --- | --- |
| `#form-roi_{uuid}`, `#form-tripwire_{uuid}` | Editor card root (`for` → SVG group id) |
| `.roi-title`, `.tripwire-title` | Name inputs |
| `.roi-remove`, `.tripwire-remove` | Remove |
| `.roi-volumetric`, `.roi-height`, `.roi-buffer` | Region extras |
| `.green_min`, `.yellow_min`, `.red_min`, `.range_max` | Occupancy sectors |
| SVG `g.roi` / `g.tripwire`, classes `adding-roi` / `adding-tripwire` | Geometry groups |

## Cameras / sensors on scene

| Pattern | Role |
| --- | --- |
| `.snapshot-image[topic]`, `#rate-{sensorId}`, `.camera-card` | Camera strip |
| `.singleton`, `.area-json`, `.sensor-id` | Sensor marks |

## `window` APIs (scene detail)

| API | Owner | Notes |
| --- | --- | --- |
| `fitSceneMapDisplay` | map | Layout resize |
| `numberRois` / `numberTripwires` | map | Labels |
| `stringifyRois` / `stringifyTripwires` | map → hidden JSON | Phase 1+ typed model still writes these |
| `getRoiValues` / `saveRois` | map / save | Save entry |
| `ssPersistGeometry` | React sets | REST bulk sync |
| `ssMap` | Phase 1+ facade | Prefer over ad-hoc globals |
| `ssRoiEditors` | React sets | addRoi / addTripwire / has* |
| `ssRefreshCameraSnapshots` / `ssDrawSingletonSensors` | React / map | |
| `ssToast` / `ssConfirm` / `ssSceneTelemetry` | React | |
| `ssMqttClient` | MQTT | Live connection |

### Custom events

`ss-roi-form-add`, `ss-tripwire-form-add`, `ss-scene-rate`, `ss-camera-rate`,
`ss-telemetry-clear`, `ss-map-host-ready`

## Calibrate postMessage (same-origin)

Calibrate iframes are retired. React sheets own calibrate UX. Historical
`ss-calibrate-*` types below are unused on scene detail after Phase 2/3.

| Type | Former direction |
| --- | --- |
| `ss-calibrate-save-points` | parent → iframe |
| `ss-calibrate-done` | iframe → parent |
| `ss-calibrate-optics` / `ss-calibrate-optics-set` | bi-di |
| `ss-calibrate-dirty` | iframe → parent |
| `ss-calibrate-layout` | parent → iframe |
| `ss-calibrate-cancel` | iframe → parent |

## Retired (Phase 5+)

| Former | Replacement |
| --- | --- |
| `#roi-form` POST | `window.ssPersistGeometry` → REST |
| Sensor / camera calibrate iframes | React panels |
| Form scrape stringify as save source | Typed `ssMap` geometry model |

## REST persist

- Regions: `GET/POST/PUT/DELETE /api/v1/region(s)`
- Tripwires: `GET/POST/PUT/DELETE /api/v1/tripwire(s)`
- Sensors: `PUT /api/v1/sensor/{uid}` (area, points, color_ranges)
- Cameras: `PUT /api/v1/camera/{uid}` (intrinsics, transforms, …)
