---
name: manager-ui
description: >-
  Manager React UI conventions — layout shells, tokens, hard DOM/window
  contracts, and build path. Use when editing manager/frontend, scene detail,
  admin lists, sheets, static/ui islands, or Manager chrome.
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->
# Manager UI

## Package layout

- Django: `manager/backend/` (`manage.py` beside `manager/`)
- React/Vite islands: `manager/frontend/`
- Built assets: `manager/backend/manager/static/ui/` via
  `{% static 'ui/…' %}`
- Build: `make -C manager ui-build` (or `SKIP_UI=1`). Details:
  `manager/frontend/README.md`
- Remaining epics: `.github/plans/manager-ui.md`

Do **not** reopen Snap / calibrate iframe work. Do **not** stretch the scene
map (`slice` / cover); keep `meet` aspect.

## Layout shells

Two intentional shells — do not force one width on both. Navbar stays
edge-to-edge; continuity is tokens / chrome, not matching content max-width.

| Shell | Pages | Layout |
| --- | --- | --- |
| **Browse column** | Cameras, Sensors, Object Library, Models | Centered `--ss-form-card-max-wide` (64rem); `.ss-admin-list` / `.ss-models-dir` |
| **Workspace** | Scene detail (2D); future React 3D | Full-bleed (`max-width: 100%`) |

**Do not:** clamp scene detail (or 3D) to 64rem; stretch browse tables
full-bleed; half-measure (capped header + full-bleed map). Scenes Home is a
thumbnail gallery (neither shell’s width rule).

## Tokens

Canonical `--ss-*` light/dark vars live in
`manager/frontend/src/tokens/ss-tokens.css`. `make -C manager ui-build`
copies that file to `manager/backend/manager/static/css/tokens.css` (Django
pages load it via the `style.css` barrel and must not depend on Node).
React islands import the same file through `tokens/tokens.css`. Edit
`ss-tokens.css` only; do not hand-edit the static copy. Do not add a
ViPPET/OEP design-system npm dependency until license/versioning are
confirmed.

## Global CSS (`static/css/`)

Django/Bootstrap chrome is split under `manager/backend/manager/static/css/`.
[`base.html`](../../manager/backend/manager/templates/sscape/base.html) still
loads a single `{% static 'css/style.css' %}` barrel:

| File | Role |
| --- | --- |
| `style.css` | `@import` barrel only |
| `tokens.css` | Synced `--ss-*` tokens |
| `bootstrap-theme.css` | Bootstrap + theme toggle / nav |
| `chrome.css` | Forms, page headers, modals, toasts |
| `map-scene.css` | Map SVG, scene panels, list camera cards, marks |
| `auth.css` | Sign-in shell |
| `legacy.css` | Embed / calibrate host + base `body` |
| `scenescape.css` | 3D viewport only (`base_3d.html`) |

React island CSS stays in `manager/frontend` → bundled `static/ui/manager-ui.css`.
Do not re-merge workspace strip rules into Django CSS without an audit.

## Entity chrome (scene detail)

- Cameras: strip cards in `#ss-cameras-mount` (`.camera-card.count-item`);
  Edit / card image → calibrate (`?ss=calibrate-*`), not a metadata drawer.
- Sensors: compact `.ss-tab-row.singleton.count-item` in `#ss-sensors-mount`.
- Children: same card chrome as cameras
  (`.camera-card.child-card.count-item` in `#ss-children-mount`). Edit →
  `?ss=child-edit&id={restUid}` (`ChildSheet`). `restUid` is local Scene
  UUID, `remote_child_id`, or ChildScene pk — ManageThing `_parse_uid` /
  `_resolve_thing` accept pk **or** UUID.
- Children tab badge: `.count-item` on cards; `numberTabs()` counts
  `.ss-tab-row, .count-item, .ss-control-card` under `#ss-children-mount`.
- Scene settings: `#scene-edit` → `?ss=scene-manage`.
- Calibrate / manage Save is dirty-gated (`Save` / `Saved` / `Saving…`).

## Hard contracts (freeze)

Stable DOM ids, `window` APIs, and events that UI tests and hybrid bridges
depend on. Change only with matching test updates in the same PR. Do not
rename `#ss-admin-list-root`, table action hrefs, or map ids below.

### Map host

| Id / selector | Role |
| --- | --- |
| `#ss-map-host` | Map parking / adopt root |
| `#map` | Map image container |
| `#svgout` | Visible map SVG (React when `ssUseReactMap`; Snap keeps `#svgout-snap`) |
| `#scale` | Scene scale |
| `#scene` | Scene id / metadata |
| `#fullscreen`, `#show-trails`, `#coloring-switch` | Map chrome |
| `#id_rois`, `#tripwires` | Hidden geometry JSON |
| `#id_child_rois`, `#child_tripwires`, `#child_sensors` | Child overlay JSON |

### Toolbar / tabs

`#new-roi`, `#save-rois`, `#empty-new-roi`, `#new-tripwire`, `#save-trips`,
`#empty-new-tripwire`, `#live-view`, `#show-telemetry`,
`#regions-tab`, `#tripwires-tab`, `#cameras-tab`, `#sensors-tab`,
`#children-tab`, `#regions`, `#trips`, `#roi-fields`, `#tripwire-fields`,
`#no-regions`, `#no-tripwires`, `#mqtt_status`, `#broker`, `#scene-edit`,
`#3d-view`.

### ROI / tripwire cards

`#form-roi_{uuid}`, `#form-tripwire_{uuid}`; `.roi-title`, `.tripwire-title`,
`.roi-remove`, `.tripwire-remove`, `.roi-volumetric`, `.roi-height`,
`.roi-buffer`, `.green_min`, `.yellow_min`, `.red_min`, `.range_max`;
SVG `g.roi` / `g.tripwire`, `adding-roi` / `adding-tripwire`.

### Cameras / sensors / children

| Pattern | Role |
| --- | --- |
| `#ss-cameras-mount`, `.snapshot-image[topic]`, `#rate-{sensorId}`, `.camera-card` | Camera strip |
| `#ss-sensors-mount`, `.singleton`, `.area-json`, `.sensor-id` | Sensors |
| `#ss-children-mount`, `.child-card`, `#mqtt_status_remote_{id}` | Children |
| `?ss=child-edit&id={restUid}` | ChildSheet |

### 3D chrome (legacy viewport)

`#scene-detail-link`, `#scene-detail-button` → `sceneDetail`;
`#2d-button`, `#3d-button` orthographic / perspective.

### Navbar

`#nav-docs` (OEP published docs), `#ss-theme-toggle`.

### `window` APIs

`fitSceneMapDisplay`, `numberRois` / `numberTripwires`,
`stringifyRois` / `stringifyTripwires`, `getRoiValues` / `saveRois`,
`ssPersistGeometry`, `ssMap`, `ssRoiEditors`,
`ssRefreshCameraSnapshots` / `ssDrawSingletonSensors` /
`ssRemoveSingletonSensor`, `ssToast` / `ssConfirm` / `ssSceneTelemetry`,
`ssMqttClient`.

Events: `ss-roi-form-add`, `ss-tripwire-form-add`, `ss-scene-rate`,
`ss-camera-rate`, `ss-telemetry-clear`, `ss-map-host-ready`,
`ss-tab-counts`, `ss-scene-tab`.

### REST (Manager persist)

Regions / tripwires CRUD; sensor PUT/DELETE; camera PUT; child
`GET/POST /api/v1/child/{uid}` (pk, `child_id`, or `remote_child_id`);
models `GET/POST/DELETE /api/v1/model-directory/`; assets include
`mark_color`.
