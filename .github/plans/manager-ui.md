<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI

Status of the Manager React rewrite against the current tree. Tokens,
primitives, hard contracts, and build notes stay at the bottom.

Package layout (as of the backend/frontend split): Django lives under
`manager/backend/`; React/Vite islands under `manager/frontend/`; built
assets still land in `manager/backend/manager/static/ui/` and load via
`{% static 'ui/…' %}`.

Do not reopen Snap / calibrate iframe work. Do not stretch the scene map
(`slice` / cover).

## Layout shells (rule of thumb)

Manager uses **two intentional page shells**. Do not force one width on
both. Navbar / logout stay edge-to-edge in either shell; continuity comes
from shared chrome (title scale, breadcrumbs, tokens, actions), not from
matching content max-width.

| Shell | Pages | Layout | Why |
| --- | --- | --- | --- |
| **Browse column** | Cameras, Sensors, Object Library, Models | Centered `--ss-form-card-max-wide` (64rem); same padding rhythm (`.ss-admin-list`, `.ss-models-dir`) | Tables / trees need a readable mid-page focus band |
| **Workspace** | Scene detail (2D); future React 3D | Full-bleed shell (`max-width: 100%`); map + side panels use the width | Spatial canvas needs horizontal room |

**Rule:** catalog / browse → browse column; spatial workspace → full shell.

**Do not**

- Clamp scene detail (or 3D) to 64rem.
- Stretch browse tables full-bleed to “match” the map.
- Half-measure (capped header + full-bleed map) — usually looks broken.

**Optional later (not required):** left-align the browse column instead of
centering if the center↔edge jump still feels sharp; still do not cap the
workspace.

Scenes Home stays a thumbnail gallery (neither shell’s width rule).

## Status

| Area | State |
| --- | --- |
| Source layout (`backend/` + `frontend/`) | **Done** |
| 2D React rewrite (Phases 0–5) | **Done** |
| Model directory UI parity | **Done** |
| Theme toggle + track-mark contrast | **Done** |
| Layout shells (browse vs workspace) | **Done** (codified; shipped) |
| Empty space — admin lists (Phase 1) | **Done** (browse column) |
| Empty space — scene detail chrome (Phase 2) | **Done** (workspace; `--ss-surface` stage) |
| Empty space — models/list consistency (Phase 3) | **Done** (shared browse column) |
| 3D scene viewport (React) | **Not started** (legacy Three.js; chrome polish shipped) |

## Done

### Source layout

Django package at `manager/backend/manager/` (`manage.py` beside it).
React package at `manager/frontend/`. Container runtime path remains
`/home/scenescape/Scenescape/manager`. Build via `make -C manager ui-build`
(or `SKIP_UI=1`).

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
- Cap already `max-width: var(--ss-form-card-max-wide)` / 64rem centered
  (`.ss-models-dir`); Cameras / Sensors / Object Library use the same
  focus column (`.ss-admin-list`).

Optional later: K8s-only BAT for browse + upload.

Key paths: `manager/frontend/src/models/`, `models-directory-main.tsx`,
`model/model_list.html`, `model_directory_view.py`, `ModelListView` in
`views.py`.

### Theme, docs, track marks, layout shells

- Light / dark theme toggle in the navbar (`#ss-theme-toggle`,
  `localStorage` key `ss-theme`, `html[data-theme]`). Tokens live in
  `manager/frontend/src/tokens/` and `:root` / `html[data-theme]` in
  `style.css`.
- Documentation nav opens published OEP docs
  (`https://docs.openedgeplatform.intel.com/dev/scenescape/index.html`),
  not a WebUI-hosted HTML tree.
- Map track marks: person/vehicle cores are a 4-quadrant checkerboard
  (Object Library `mark_color` alternating with the track UUID color) so
  marks stay readable on light and dark maps. AprilTags stay circle
  cores. Object Library sheet exposes **Mark color**.
- **Browse column** (Cameras, Sensors, Object Library, Models): centered
  64rem (`--ss-form-card-max-wide`), matching padding, quieter titles
  (`--ss-type-workspace-title`), denser empty states; Actions hug chips.
- **Workspace** (scene detail): full-bleed; `.scene-map-stage` fills with
  `--ss-surface` (no transparent hole). Do not unify width with browse.
- See [Layout shells](#layout-shells-rule-of-thumb).

### 3D chrome (still legacy viewport)

React 3D rewrite is not started, but 3D templates already deep-link into
the 2D React surfaces:

- Scene name `#scene-detail-link` and wrench `#scene-detail-button` →
  `sceneDetail`.
- Per-camera wrench → `/{scene.id}/?ss=calibrate-cam&id=…`.

## Remaining

Work left is the 3D epic. Empty-space / layout-shell work is closed (see
[Layout shells](#layout-shells-rule-of-thumb) and Done). When porting 3D,
keep it on the **workspace** shell — full-bleed, not the browse column.

### 1. 3D scene viewport (epic)

**Not started.** Largest remaining Manager UI epic. Legacy Three.js
surface remains:

- Entry: `manager/backend/manager/static/js/scenescape3d.js` (~700 LOC) plus
  ES modules under `static/js/thing/`, `viewport.js`, managers, etc.
- Mount: `base_3d.html` loads the legacy module — no React root / no
  `manager/frontend` 3D entry.
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

### 2. Optional follow-ups (not blocking)

- K8s-only BAT for model-directory browse + upload.
- How-to updates only when chrome labels, open paths, or nav targets
  change (see `docs/user-guide/how-to-guides/`).
- Left-align browse column (still 64rem) if centered↔workspace jump still
  feels sharp after living with it.

## Tokens

Mirror `--ss-*` / `ss.*` in `manager/frontend/src/tokens/` (same values as
`:root` / `html[data-theme]` in `manager/backend/manager/static/css/style.css`).
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
| `geospatial/scene-form.js`, `geospatial.css` | React `SceneManagePanel` / `GeospatialMapPicker` |
| `childscene.js`, Django scene/asset/child form helpers in `sscape.js` | React sheets (`ChildSheet`, `AssetSheet`, `SceneManagePanel`) |
| `form_back.html`, `singletonArea.html`, `logo.png` | React `PageHeader` back; sensor area sheet; `intel-logo.svg` |

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

Islands under `manager/backend/manager/static/ui/`: `scene-detail`,
`scenes-home`, `list-sheets`, `admin-list`, `destructive-actions`,
`models-directory` (+ shared `manager-ui.css`).

Package and developer notes: `manager/frontend/README.md`. Plan ownership for
remaining empty-space / 3D work stays in this file.
