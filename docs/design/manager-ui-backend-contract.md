<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Design Document: Manager UI backend contract

- **Author(s)**: SceneScape maintainers
- **Date**: 2026-09-29
- **Status**: `Accepted`
- **Related**: [ADR 19: Host-Independent Manager UI](../adr/0019-host-independent-manager-ui.md),
  [`.github/skills/manager-ui/SKILL.md`](../../.github/skills/manager-ui/SKILL.md)

---

## 1. Overview

Freeze the wire contract the Manager React islands need so the UI can evolve
against documented HTTP, bootstrap JSON, and MQTT shapes. Django remains the
current host; a future API host (for example FastAPI) must satisfy this
contract. Hard DOM / `window.ss*` bridges are **debt to retire**, not the
long-term boundary.

## 2. Goals

- Document bootstrap payloads, REST paths the islands call, auth modes, and
  MQTT topic patterns the 2D UI depends on.
- Give UI tests and backend implementers one source of truth for compatibility.
- Separate portable surfaces (Token REST, MQTT) from transitional ones
  (session-only legacy forms, template DOM parking).

## 3. Non-Goals

- Replacing Django in this document.
- Rewriting Scene Controller, tracker, or MQTT broker semantics.
- Freezing legacy 3D (`base_3d.html` / `scenescape3d.js`) beyond shared auth
  and topic families — that is the separate 3D epic.

## 4. Background / Context

Islands already prefer `json_script` bootstrap + `/api/v1` Token auth over
server-rendered forms. Template sibling DOM still binds some UI to Django’s
request cycle. OpenAPI at
[`docs/user-guide/api-docs/api.yaml`](../user-guide/api-docs/api.yaml) covers
entity CRUD; it does not define island bootstrap or MQTT UI topics.

## 5. Proposed Design

### 5.1 Islands and bootstrap scripts

| Island | Mount | Bootstrap `id` |
| --- | --- | --- |
| Chrome (nav/about/theme) | `#ss-chrome-root` | `GET …/ui-bootstrap/?page=chrome` |
| Scenes home | `#ss-scenes-home-app` | `GET …/ui-bootstrap/?page=scenes` (optional `ss-scenes-home-bootstrap`) |
| Scene detail | `#ss-scene-detail-root` | `GET …/ui-bootstrap/?page=scene&id=` (optional `ss-scene-detail-bootstrap`) |
| Admin lists | `#ss-admin-list-root` | `GET …/ui-bootstrap/?page=cameras\|sensors\|assets` |
| List sheets | (query-driven; no dedicated root) | `GET …/ui-bootstrap/?page=list-sheets&id=cam\|sensor\|asset` |
| Models directory | `#ss-models-directory-root` | `GET …/ui-bootstrap/?page=models` |
| Sign-in | `#ss-sign-in-root` | `GET …/ui-bootstrap/?page=sign-in` |
| Destructive actions | creates `#ss-destructive-actions-root` | none |

#### Chrome (`page=chrome`)

Manager pages load chrome via the bootstrap API (no embedded `json_script`).

- `authenticated`, `username`, `isStaff`, `isKubernetes`
- `appName`, `appVersion`, `appGitCommit`, `docsVersion`
- `urls` `{ home, scenes, cameras, sensors, models, assets, admin,
  signOut, docs, support, intel, intelLogo }`
- `activeNav?` — `scenes` \| `cameras` \| `sensors` \| `models` \| `assets`

#### Host-independent bootstrap API

`GET /api/v1/ui-bootstrap/?page=chrome|scenes|scene|cameras|sensors|assets|models|list-sheets|sign-in&id=`
returns the same JSON shapes documented below (Session or Token).
Static shell: `manager/backend/manager/static/ui/shell.html` + `spa.js`
(and `sign-in.html` + `sign-in.js`; see `manager/frontend/README.md`).
For `list-sheets`, `id` is `cam` \| `sensor` \| `asset`. For `scene`, `id`
is the scene UUID. `chrome` and `sign-in` are anonymous.

Scene detail also exposes `google-maps-api-key` and `mapbox-api-key`
`json_script` nodes (string scalars).

Canonical TypeScript shapes live under `manager/frontend/src/`
(`scene/types.ts`, `scenes/ScenesHomeApp.tsx`, list entry modules). Hosts
must keep field names below stable or update islands + this doc together.

#### Scenes home (`page=scenes` / optional `ss-scenes-home-bootstrap`)

Manager Django pages load this via the bootstrap API (no embedded
`json_script`). Static shells and tests may still embed the script tag.

- `authToken` (string) — DRF Token key
- `isSuperuser` (boolean)
- `scenes[]`: `id`, `name`, `georeferenced`, `thumbnailUrl`, `mapUrl`,
  `detailUrl`, `detail3dUrl`, `manageUrl`, `deleteUrl` (nullable),
  `counts` `{ sensors, regions, tripwires }`

#### Scene detail (`page=scene` / optional `ss-scene-detail-bootstrap`)

Manager Django pages load this via the bootstrap API. Template still
supplies `#scene` (hidden) and map API key `json_script` nodes for legacy
geospatial plugins / `sscape.js` until those move behind React.

- `scene`: `id`, `name`, `scale`, `mapUrl`, `thumbnailUrl`, `wssConnection?`,
  `outputLla?`, `georeferenced?`
- `cameras[]`: `id`, `sensorId`, `name`, `calibrateHref`, `cmdTopic`,
  `deleteUrl`
- `sensors[]`: `id`, `sensorId`, `name`, `iconUrl`, `areaJson`,
  `calibrateHref`, `editHref`, `deleteUrl`
- `children[]`: `id`, `name`, `childType`, `remoteChildId`, `detailUrl`,
  `thumbnailUrl`, `mapUrl`, `restUid`, `editHref`, `deleteUrl`
- `regions`, `tripwires` — geometry JSON arrays
- `assetMarkColors` — map of asset name → mark color
- `counts` `{ sensors, regions, tripwires, children }`
- `urls` `{ scenesHome, camList?, sensorList?, scene3d, sceneEdit,
  sceneDelete, camCreate }`
- `authToken`, `isSuperuser`, `isKubernetes`
- `appVersion`, `appGitCommit?`
- `googleMapsApiKey?`, `mapboxApiKey?`
- `deleteImpact?` `{ sensors, regions, tripwires }`
- `childRoiJson?`, `childTripwireJson?`, `childSensorJson?` — JSON strings
  for legacy child overlay hidden inputs (created by `ensureSceneDetailDom`)
- `scenes[]` for pickers: `id`, `name`, `georeferenced?`, `mapUrl?`

#### Admin list (`page=cameras|sensors|assets`)

Manager list pages load via the bootstrap API (no embedded `json_script`).

- `title`, `breadcrumbs[]`, `primaryAction?` `{ label, href, id? }`
- `columns[]`, `rows[]` (`id`, `cells[]`, `actions[]`), `emptyMessage`,
  `isSuperuser`
- No `authToken` (sheets bootstrap carries Token)

#### List sheets (`page=list-sheets&id=cam|sensor|asset`)

- `authToken`, `isSuperuser`, `kind` (`cam` | `sensor` | `asset`)
- `defaultSceneId`, `isKubernetes`
- `cameras?` / `sensors?`: `id`, `sensorId`, `name`, `sceneId?`
- `scenes[]`: `id`, `name` (empty for assets)

#### Models directory (`page=models`)

- `isSuperuser` only — tree loaded via Token model-directory API

#### Sign-in (`page=sign-in`)

- `appName`, `appVersion`, `intelLogo`, `intelHref`, `nextUrl?`, `docsVersion?`
- Island posts to `POST /sign_in/` with `Accept: application/json` (session +
  CSRF); success returns `{ ok, redirect }`

#### Sheet deep links

Query `?ss=<action>&id=<optional>` — see
`manager/frontend/src/lib/sheetQuery.ts`. Actions include
`cam-create|cam-edit|sensor-create|sensor-edit|child-create|child-edit|
scene-create|scene-edit|scene-manage|scene-import|asset-create|asset-edit|
calibrate-cam|calibrate-sensor`.

### 5.2 Auth (portable vs transitional)

| Mode | How | Used for | Portable? |
| --- | --- | --- | --- |
| Token | `Authorization: Token <authToken>` from bootstrap / `ss-auth-bootstrap` | `/api/v1` CRUD, deletes, model-directory, mesh via `lib/rest.ts` / `lib/restDelete.ts` / `modelDirectoryApi.ts` / `meshGeneration.ts` | **Yes** — long-term |
| Session + CSRF | cookie + `X-CSRFToken` via `lib/session.ts` | Rare session-only legacy forms | **No** — transitional |
| Session cookie | `credentials: "same-origin"` | Page shell, media, static | Host concern |

Login today is Django session (`sign_in/`); Token is issued for the signed-in
user and injected as `ss-auth-bootstrap` (all authenticated pages) plus
island bootstraps. `POST /api/v1/auth` exists for API clients. New island
code must use `lib/rest.ts`, `lib/session.ts`, and `lib/restDelete.ts` — do
not parse CSRF cookies or assume `#ss-csrf-form` in feature modules.

Entity deletes from the UI use `DELETE /api/v1/{camera\|sensor\|scene\|child\|asset}/{uid}`
(ManageThing) via `lib/restDelete.ts`. Django DeleteView URLs remain as link
hrefs for bookmarks; the destructive-actions interceptor maps those paths to
Token REST and never POSTs the DeleteView.

### 5.3 REST the UI calls

Base: `/api/v1`. Client: `manager/frontend/src/lib/rest.ts`.

| Area | Methods / paths |
| --- | --- |
| Camera | `POST /camera`, `GET|PUT /camera/{uid}` |
| Sensor | `POST /sensor`, `GET|PUT|DELETE /sensor/{uid}` |
| Child | `POST /child`, `GET|PUT /child/{uid}`, `POST /childscene/preview-geospatial-transform/` |
| Scene | `POST /scene`, `GET|PUT /scene/{uid}`, `GET /scenes`, `POST /import-scene/` |
| Region | `GET /regions?scene=`, `POST /region`, `PUT|DELETE /region/{uid}` |
| Tripwire | `GET /tripwires?scene=`, `POST /tripwire`, `PUT|DELETE /tripwire/{uid}` |
| Asset | `POST /asset`, `GET|PUT /asset/{uid}` |

**Transitional (not Token CRUD yet):**

| Call | Path | Auth |
| --- | --- | --- |
| Model directory | `/api/v1/model-directory/` | Token |
| Mesh generate / status | `/api/v1/scene/{uuid}/generate-mesh/`, `…/generate-mesh-status/` | Token |
| Mapping status | `/mapping-service/status/` | Token |
| Deletes | bootstrap `deleteUrl` / DeleteView href → Token `DELETE /api/v1/...` | Token |
| Media | `thumbnailUrl` / `mapUrl` / `/media/…` | Session |

OpenAPI details: [`api.yaml`](../user-guide/api-docs/api.yaml). Breaking path
or payload changes require island + OpenAPI + this doc updates in the same
change.

### 5.4 MQTT (2D UI)

Transport: WSS broker URL (`scene.wssConnection` / `wss://{host}/mqtt`).
App prefix: `scenescape`. Scene-detail React owns connect (`src/mqtt`) and
assigns `window.ssMqttClient`; Snap mark/event handlers attach via
`ssAttachSceneMqttClient`. Calibrate / Snap-map pages still wire MQTT in
`sscape.js` (not a React island contract).

| Direction | Pattern | Role |
| --- | --- | --- |
| Sub | `scenescape/regulated/scene/{sceneId}` | Scene telemetry |
| Sub | `scenescape/event/+/` + `{sceneId}` + `/+/+` | Region / tripwire events |
| Sub | `scenescape/sys/child/status/+` | Remote child connectivity |
| Sub | `scenescape/image/camera/+` | Live camera strip |
| Sub | `scenescape/image/calibration/camera/{sensorId}` | Calibrate |
| Pub | `scenescape/cmd/camera/{sensorId}` | `getimage` / calibration cmds |
| Pub | `scenescape/sys/child/status/{remoteId}` | `isConnected` probe |

New ROI / tripwire topics created in UI:

- `scenescape/event/region/{sceneId}/{uuid}/count`
- `scenescape/event/tripwire/{sceneId}/{uuid}/objects`

### 5.5 Domain services (map)

Scene map upload processing lives in
`manager/backend/manager/services/scene_map.py` (`auto_align_uploaded_map`,
`save_scene_thumbnail`, `finalize_scene_map`, `apply_map_on_scene_create`).
`Scene.save()` and `SceneSerializer` call these helpers so map/align/thumbnail
logic is not trapped only inside the model `save()` hook. Mesh **generation**
alignment remains in `mesh_generator` (honors `_from_generate_mesh`).

### 5.6 DOM / window debt (retire, do not extend)

**Scene detail template** only supplies bootstrap `json_script` nodes and
`#ss-scene-detail-root`. Map host (`#ss-map-host`, `#map-controls`, `#map`,
`#svgout`, geometry hiddens) is created from bootstrap by
`ensureSceneDetailDom` before React mounts so `sscape.js` still finds the
same hard-contract ids.

Until hybrid legacy JS is gone, those ids and `window.ss*` bridges remain
required at runtime — but they are **not** Django template siblings. Full
freeze tables live in the manager-ui skill. React call sites use
`manager/frontend/src/lib/legacyBridge.ts` rather than ad-hoc `window.*`.
**New UI must not add** required template sibling ids or new `window.ss*`
APIs; prefer bootstrap + fetch + React-owned mounts.

Long-term host shape: a single root per page + bootstrap JSON (or equivalent
config endpoint) + Token REST + MQTT — no CSRF deletes, no map parking.

## 6. Alternatives Considered

- **OpenAPI only** — Rejected as sole freeze; bootstrap and MQTT UI topics are
  out of scope for `api.yaml`.
- **DOM ids as the contract** — Rejected as destination; kept as transitional
  debt while hybrid legacy JS remains.
- **Immediate FastAPI swap** — Rejected until this contract is green under
  Django and template DOM coupling is retired.

## 7. Risks and Mitigations

- **Drift** — Treat TS bootstrap types + this doc + OpenAPI as one change set
  when fields move.
- **Mesh via Token only** — UI and setup scripts use `/api/v1/scene/…/generate-mesh[-status]/`.
- **MQTT shared client** — React owns connect and live marks on scene detail;
  Snap still draws child overlays via `ssAttachSceneMqttClient` until a
  children/marks epic retires the overlay.

## 8. Rollout / Migration Plan

1. Land this doc + `lib/session.ts` / `lib/bootstrap.ts` helpers (done with
   first implementation PR).
2. Shrink skill hard-contract tables as React owns chrome.
3. Replace CSRF callers with Token REST when endpoints exist.
4. Only then: serve SPA from a non-Django host pointed at the same contract.

## 9. Open Questions

- Prefer path-based nginx `try_files` vs Django serving `shell.html` for `/`?
