<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI

2D React rewrite (Phases 0–5) is **done**: tokens, primitives, scene detail,
lists, sheets, calibrate panels, REST geometry persist, in-place entity
cards. This file is the remaining work plus freeze contracts.

Do not reopen Snap / calibrate iframe work. Do not stretch the scene map
(`slice` / cover).

## Remaining

### 1. Empty space on lists and scene detail

Status: **not started**. Design agreed; implement in a later PR. Do not
fold into 3D or model-directory work.

Two layout mistakes produce the same complaint (“large empty spaces”) on a
wide monitor.

**Admin lists** (Cameras, Sensors, Object Library) are 1–3 short columns
plus actions in `container-fluid`. Columns share leftover width equally,
so gaps sit *between* Name / ID / Scene. Title is landing-page scale;
empty states sit in a hollow full-width card. Scenes Home is a thumbnail
gallery and should stay that way.

**Scene detail** letterboxing is correct (`preserveAspectRatio="xMidYMid
meet"`). What still *reads* as a hole: unused stage fill differs from the
page surface; camera preview letterbox does not match the card; empty tabs
must stay a short peek, not a padded panel.

#### Non-goals

- Do not turn Cameras / Sensors / Object Library into card galleries.
- Do not stretch the map or grow one camera card to fill the Below strip.
- Do not switch camera previews to `cover`.
- Do not add a second density control.
- Do not change Models directory into a table. Optional: align its
  max-width with the list cap after Phase 1.
- No user-facing docs unless chrome labels change.

#### Phase 1 — lists (do first)

- Cap `.ss-admin-list` / `.ss-admin-table-card` at **56–64rem**,
  left-aligned (same idea as `ss-form-card--wide`).
- Content-sized columns (`table-layout: auto`); leftover space **after**
  the last column. Actions column hugs chips.
- Quieter title (`~1.2rem`); drop title-echo breadcrumb.
- Compact empty state inside a content-sized card.
- Spot-check Cameras, Sensors, Object Library at ~1920px and ~1280px.

Likely files: `manager/ui/src/admin/AdminListApp.tsx`, `AdminListApp.css`,
`PageHeader.tsx` / `.css`, `manager/src/manager/views.py` list bootstraps.

#### Phase 2 — scene detail chrome

- Unused map stage fill → `--ss-surface` (not a contrasting hole). Keep
  `meet` and viewBox sync (`#svgout` + `#svgout-snap`).
- Keep Auto / Below / Side and map focus.
- Below camera strip: left-align cards; quiet gutter; `contain` previews
  with letterbox fill matching the card.
- Empty tabs stay `ss-empty-state`; do not pad to `--ss-panel-size`.

Likely files: `SceneDetailPage.css`, `reactSceneMap.css`,
`style.css` (`.scene-map-stage`), `CameraStrip.css`,
`ControlTabEntities.css`.

#### Phase 3 — optional

- Models directory max-width matches the list cap if it now looks
  inconsistent.
- Scenes Home unchanged.

#### Verify

- `make -C manager ui-build`
- Lists: table does not stretch across a wide viewport; columns are not
  padded mid-row.
- Scene detail: map letterboxes without a contrasting hole; marks stay on
  the image after window and splitter resize. Show Trails / Visualize ROIs
  unchanged.
- Existing UI BAT if those suites run in the implementing PR.

Out of scope here: calibrate workspace size, geospatial picker, theme
tokens, virtualized tables / search / sort / filter.

### 2. Model directory parity

Status: **done** (UI). React island on `model/list/` matches legacy actions:

- Mount: `#ss-models-directory-root` → `models-directory.js`
- Bootstrap: `#ss-models-directory-bootstrap` (`isSuperuser`)
- Browse, refresh, copy `/models/…`, download
- Superuser: create folder, upload, zip extract into named folder,
  overwrite confirm, delete confirm, drag-drop onto root/folder
- API: `GET/POST/DELETE /api/v1/model-directory/` (JSON load only)
- Legacy jQuery `model_list.js` / HTML fragment retired

Optional later: K8s-only BAT covering browse + upload if product requires it.

### 3. 3D scene viewport (epic)

Replace or wrap the legacy Three.js surface (`scenescape3d.js` ~4.3k LOC)
with a React-owned shell that reuses MQTT / auth patterns from the 2D
rewrite. Do **not** fold into 2D trickle PRs.

Precursor: non-georeferenced child linking already ships a thin Z-up
placement canvas (`manager/ui/src/placement/`) with `poseThree` conversion
and TransformControls. Reuse that pose/gizmo module in the viewport; do
not wrap `scenescape3d.js` for hierarchy placement.

Suggested slices:

1. Inventory: entry points, MQTT topics, asset load path, Django template
   mounts.
2. Thin React mount + bootstrap JSON (parity shell; keep Three under the
   hood).
3. Port interaction chrome (layers, selection, camera controls) into
   React.
4. Retire legacy script load path when UI tests cover 3D BAT.

Gate: document any new 3D contract ids in this file before deleting
legacy globals; UI BAT green for scene 3D view when that suite exists.

## Tokens

Mirror `--ss-*` / `ss.*` in `manager/ui/src/tokens/` (same values as
`:root` in `manager/src/manager/static/css/style.css`). Do not add a
ViPPET/OEP design-system npm dependency until license and versioning are
confirmed. When a shared package exists, remap names — do not restyle ad
hoc.

Primitives already landed: `Button`, `PageHeader`, `Tabs`, `Breadcrumb`,
`Card`, `StatusChip`, `TableActions`, `TextField`, `FormCard`,
`FormSection`, `Modal`, `Drawer`, `ConfirmDialog`, `Toast`.

## Hard contracts (freeze)

Stable DOM ids, `window` APIs, and postMessage types that UI tests and
hybrid bridges depend on. Change only with matching test updates in the
same PR. Do not rename `#ss-admin-list-root`, table action hrefs, or
scene map ids below.

### Scene detail — map host

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

### Scene detail — toolbar / tabs

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

### ROI / tripwire editor cards

| Pattern | Role |
| --- | --- |
| `#form-roi_{uuid}`, `#form-tripwire_{uuid}` | Editor card root (`for` → SVG group id) |
| `.roi-title`, `.tripwire-title` | Name inputs |
| `.roi-remove`, `.tripwire-remove` | Remove |
| `.roi-volumetric`, `.roi-height`, `.roi-buffer` | Region extras |
| `.green_min`, `.yellow_min`, `.red_min`, `.range_max` | Occupancy sectors |
| SVG `g.roi` / `g.tripwire`, classes `adding-roi` / `adding-tripwire` | Geometry groups |

### Cameras / sensors on scene

| Pattern | Role |
| --- | --- |
| `.snapshot-image[topic]`, `#rate-{sensorId}`, `.camera-card` | Camera strip |
| `.singleton`, `.area-json`, `.sensor-id` | Sensor marks |

### `window` APIs (scene detail)

| API | Owner | Notes |
| --- | --- | --- |
| `fitSceneMapDisplay` | map | Layout resize |
| `numberRois` / `numberTripwires` | map | Labels |
| `stringifyRois` / `stringifyTripwires` | map → hidden JSON | Typed model still writes these |
| `getRoiValues` / `saveRois` | map / save | Save entry |
| `ssPersistGeometry` | React sets | REST bulk sync |
| `ssMap` | facade | Prefer over ad-hoc globals |
| `ssRoiEditors` | React sets | addRoi / addTripwire / has* |
| `ssRefreshCameraSnapshots` / `ssDrawSingletonSensors` / `ssRemoveSingletonSensor` | React / map | |
| `ssToast` / `ssConfirm` / `ssSceneTelemetry` | React | |
| `ssMqttClient` | MQTT | Live connection |

Custom events: `ss-roi-form-add`, `ss-tripwire-form-add`, `ss-scene-rate`,
`ss-camera-rate`, `ss-telemetry-clear`, `ss-map-host-ready`,
`ss-tab-counts`, `ss-scene-tab`.

### Calibrate postMessage (historical)

Calibrate iframes are retired. React sheets own calibrate UX.
`ss-calibrate-*` types are unused on scene detail.

### Retired

| Former | Replacement |
| --- | --- |
| `#roi-form` POST | `window.ssPersistGeometry` → REST |
| Sensor / camera calibrate iframes | React panels |
| Form scrape stringify as save source | Typed `ssMap` geometry model |

### REST persist

- Regions: `GET/POST/PUT/DELETE /api/v1/region(s)`
- Tripwires: `GET/POST/PUT/DELETE /api/v1/tripwire(s)`
- Sensors: `PUT /api/v1/sensor/{uid}` (area, points, color_ranges);
  `DELETE /api/v1/sensor/{uid}`
- Cameras: `PUT /api/v1/camera/{uid}` (intrinsics, transforms, …)

## Build

```bash
make -C manager ui-build
```
