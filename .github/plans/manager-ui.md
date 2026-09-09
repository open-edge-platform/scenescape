<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI

Status of the Manager React rewrite against the current tree. Tokens,
primitives, hard contracts, and build notes stay at the bottom.

Do not reopen Snap / calibrate iframe work. Do not stretch the scene map
(`slice` / cover).

## Status

| Area | State |
| --- | --- |
| 2D React rewrite (Phases 0–5) | **Done** |
| Model directory UI parity | **Done** |
| Theme toggle + track-mark contrast | **Done** |
| Empty space — admin lists (Phase 1) | **Not started** |
| Empty space — scene detail chrome (Phase 2) | **Partial** |
| 3D scene viewport (React) | **Not started** (legacy Three.js; chrome polish shipped) |

## Done

### 2D rewrite

Tokens, primitives, scene detail workspace, lists island, sheets,
calibrate panels, REST geometry persist, in-place entity cards (cameras /
sensors / children create + delete without full-page flash), live tab
counts via `ss-tab-counts`, map `meet` aspect (no stretch).

Scene entity cards: camera/sensor **Edit** (and the camera card image)
opens the calibrate workspace (`calibrateHref` / `?ss=calibrate-*`), not
a separate metadata drawer. Scene settings: pencil `#scene-edit` →
`?ss=scene-manage` (`SceneManagePanel`, title **Edit Scene**).

Calibrate / manage Save buttons are dirty-gated (`Save` / `Saved` /
`Saving…`), not legacy “Save Camera” / “Save Sensor” labels.

### Model directory

React island on K8s `model/list/`:

- Mount: `#ss-models-directory-root` → `models-directory.js`
- Bootstrap: `#ss-models-directory-bootstrap` (`isSuperuser`)
- Browse, refresh, copy `/models/…`, download
- Superuser: create folder, upload, zip → folder named after archive then
  extract, overwrite confirm, delete confirm, drag-drop onto root/folder
- API: `GET/POST/DELETE /api/v1/model-directory/` (JSON load only)
- Legacy `model_list.js` and `model/includes/model_directory.html` removed
- Cap already `max-width: 64rem` (`.ss-models-dir`)

Optional later: K8s-only BAT for browse + upload.

Key paths: `manager/ui/src/models/`, `models-directory-main.tsx`,
`model/model_list.html`, `model_directory_view.py`, `ModelListView` in
`views.py`.

### Theme, docs nav, track marks

- Light / dark theme toggle in the navbar (`#ss-theme-toggle`,
  `localStorage` key `ss-theme`, `html[data-theme]`). Tokens live in
  `manager/ui/src/tokens/` and `:root` / `html[data-theme]` in
  `style.css`.
- Documentation nav opens published OEP docs
  (`https://docs.openedgeplatform.intel.com/dev/scenescape/index.html`),
  not a WebUI-hosted HTML tree.
- Map track marks: person/vehicle cores are a 4-quadrant checkerboard
  (Object Library `mark_color` alternating with the track UUID color) so
  marks stay readable on light and dark maps. AprilTags stay circle
  cores. Object Library sheet exposes **Mark color**.

### 3D chrome (still legacy viewport)

React 3D rewrite is not started, but 3D templates already deep-link into
the 2D React surfaces:

- Scene name `#scene-detail-link` and wrench `#scene-detail-button` →
  `sceneDetail`.
- Per-camera wrench → `/{scene.id}/?ss=calibrate-cam&id=…`.

## Remaining

### 1. Empty space on lists and scene detail

Two layout mistakes produce the same complaint (“large empty spaces”) on a
wide monitor. Do not fold into the 3D epic.

#### Phase 1 — admin lists — **not started**

Cameras, Sensors, Object Library still full-bleed in `container-fluid`.
Columns share leftover width equally (gaps *between* Name / ID / Scene).
Title is landing-page scale (`1.75rem`). Empty states sit in a hollow
full-width card. Scenes Home is a thumbnail gallery and should stay that
way.

Still to do:

- Cap `.ss-admin-list` / `.ss-admin-table-card` at **56–64rem**,
  left-aligned (same idea as `ss-form-card--wide` / models at `64rem`).
- Content-sized columns (`table-layout: auto`); leftover space **after**
  the last column. Actions column hugs chips.
- Quieter title (`~1.2rem`). Title-echo breadcrumb strip already exists in
  `PageHeader` (`wayfindingCrumbs`); Django still passes echo crumbs.
- Compact empty state inside a content-sized card.
- Spot-check Cameras, Sensors, Object Library at ~1920px and ~1280px.

Likely files: `manager/ui/src/admin/AdminListApp.tsx`, `AdminListApp.css`,
`PageHeader.tsx` / `.css`, `manager/src/manager/views.py` list bootstraps.

Current evidence of open work: `.ss-admin-list` / `.ss-admin-table-card`
are `width: 100%` with no `max-width`; no `table-layout` on
`.ss-admin-table`; `.ss-page-title` is `1.75rem`; `.ss-table-empty` uses
large padding inside the full-width card.

#### Phase 2 — scene detail chrome — **partial**

Letterboxing is correct (`preserveAspectRatio="xMidYMid meet"` on the
React map; Snap overlay syncs PAR). Auto / Below / Side and map focus
remain. Compact empty tabs (`ss-empty-state`, workspace padding
`0.5rem 0.25rem` — not `--ss-panel-size`). Camera strip: left-aligned
cards, `object-fit: contain` default, letterbox fill
`color-mix(… --ss-surface …)` on preview frames. Adjacent React map
surfaces already use `--ss-surface` (`SceneMapPane.css`,
`reactSceneMap.css`).

Still open:

- Named `.scene-map-stage` in `style.css` is still `background:
  transparent` — unused stage fill can still read as a hole vs the page
  surface. Align to `--ss-surface` without changing `meet` or viewBox
  sync (`#svgout` + `#svgout-snap`).
- Re-check Below strip gutter / card alignment if anything still feels
  hollow after the stage fill fix.

Likely files: `style.css` (`.scene-map-stage`), `SceneDetailPage.css`,
`reactSceneMap.css`, `SceneMapPane.css`, `CameraStrip.css`,
`ControlTabEntities.css`.

#### Phase 3 — optional

- Models directory already at `64rem`. After Phase 1, confirm list cap and
  models cap look consistent (both ~56–64rem); adjust only if needed.
- Scenes Home unchanged.

#### Non-goals

- Do not turn Cameras / Sensors / Object Library into card galleries.
- Do not stretch the map or grow one camera card to fill the Below strip.
- Do not switch camera previews to `cover` as the default.
- Do not add a second density control.
- Do not change Models directory into a table.
- Update user-facing how-tos when chrome labels, open paths, or nav
  targets change (see `docs/user-guide/how-to-guides/`).

#### Verify (when implementing)

- `make -C manager ui-build`
- Lists: table does not stretch across a wide viewport; columns are not
  padded mid-row.
- Scene detail: map letterboxes without a contrasting hole; marks stay on
  the image after window and splitter resize. Show Trails / Visualize ROIs
  unchanged.
- Existing UI BAT if those suites run in the implementing PR.

Out of scope here: calibrate workspace size, geospatial picker, theme
tokens, virtualized tables / search / sort / filter.

### 2. 3D scene viewport (epic)

**Not started.** Legacy Three.js surface remains:

- Entry: `manager/src/manager/static/js/scenescape3d.js` (~700 LOC) plus
  ES modules under `static/js/thing/`, `viewport.js`, managers, etc.
- Mount: `base_3d.html` loads the legacy module — no React root / no
  `manager/ui` 3D entry.
- Scene detail links out (`#3d-view` → `urls.scene3d`). Chrome already
  deep-links back (see Done).

Replace or wrap with a React-owned shell that reuses MQTT / auth patterns
from the 2D rewrite. Do **not** fold into 2D trickle PRs (empty-space or
otherwise).

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
`:root` / `html[data-theme]` in `manager/src/manager/static/css/style.css`).
Do not add a ViPPET/OEP design-system npm dependency until license and
versioning are confirmed. When a shared package exists, remap names — do
not restyle ad hoc.

Primitives already landed: `Button`, `PageHeader`, `Tabs`, `Breadcrumb`,
`Card`, `StatusChip`, `TableActions`, `TextField`, `SelectField`,
`FormCard`, `FormSection`, `FormShell`, `Modal`, `Drawer`, `WorkspacePanel`,
`PanelLayoutToggle`, `ConfirmDialog`, `Toast`, `LegacyConfirmHost`.

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
| `#scene-edit` | Opens `?ss=scene-manage` |
| `#3d-view` | Link to legacy 3D scene |

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

### 3D template chrome

| Id | Role |
| --- | --- |
| `#scene-detail-link` | Scene name → `sceneDetail` |
| `#scene-detail-button` | Wrench → `sceneDetail` |
| `#2d-button`, `#3d-button` | Orthographic / perspective toggles in 3D |

### Navbar

| Id | Role |
| --- | --- |
| `#nav-docs` | Published OEP documentation (new tab) |
| `#ss-theme-toggle` | Light / dark theme |

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
| jQuery `model_list.js` / HTML fragment load | React `models-directory.js` + JSON API |
| WebUI-hosted Documentation tree | `#nav-docs` → OEP published docs |

### REST persist

- Regions: `GET/POST/PUT/DELETE /api/v1/region(s)`
- Tripwires: `GET/POST/PUT/DELETE /api/v1/tripwire(s)`
- Sensors: `PUT /api/v1/sensor/{uid}` (area, points, color_ranges);
  `DELETE /api/v1/sensor/{uid}`
- Cameras: `PUT /api/v1/camera/{uid}` (intrinsics, transforms, …);
  `camerachain` validated on form + REST (`validate_camerachain`)
- Models (K8s): `GET/POST/DELETE /api/v1/model-directory/`
- Assets: Object Library includes `mark_color`

## Build

```bash
make -C manager ui-build
```

Islands under `manager/src/manager/static/ui/`: `scene-detail`,
`scenes-home`, `list-sheets`, `admin-list`, `destructive-actions`,
`models-directory` (+ shared `manager-ui.css`).

Package and developer notes: `manager/ui/README.md`. Plan ownership for
remaining empty-space / 3D work stays in this file.
