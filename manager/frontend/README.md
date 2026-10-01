<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI (React island)

Vite + React + TypeScript package that builds Manager 2D islands into Django
static assets.

Conventions, layout shells, and hard DOM contracts:
[`.github/skills/manager-ui/SKILL.md`](../../.github/skills/manager-ui/SKILL.md).
Architecture decision:
[`docs/adr/0019-host-independent-manager-ui.md`](../../docs/adr/0019-host-independent-manager-ui.md).
Frozen UI↔backend contract (bootstrap, REST, auth, MQTT):
[`docs/design/manager-ui-backend-contract.md`](../../docs/design/manager-ui-backend-contract.md).

## Setup

```bash
cd manager/frontend
npm ci
```

## Build

```bash
npm run build
# or from repo:
make -C manager ui-build
```

Outputs under `manager/backend/manager/static/ui/`:

| Entry                 | Files                    | Used by                           |
| --------------------- | ------------------------ | --------------------------------- |
| shared CSS            | `manager-ui.css`         | All islands                       |
| `chrome`              | `chrome.js`              | Navbar / about / theme (all pages)|
| `spa`                 | `spa.js` + `shell.html`  | Static host (scenes + scene detail)|
| `scene-detail`        | `scene-detail.js`        | Scene detail                      |
| `scenes-home`         | `scenes-home.js`         | Scenes gallery                    |
| `list-sheets`         | `list-sheets.js`         | Cam / sensor / asset lists        |
| `admin-list`          | `admin-list.js`          | Camera / sensor list chrome       |
| `destructive-actions` | `destructive-actions.js` | In-page delete confirms           |
| `models-directory`    | `models-directory.js`    | K8s Models page (browse / upload) |

`ui-build` also copies `src/tokens/ss-tokens.css` →
`backend/manager/static/css/tokens.css` (even with `SKIP_UI=1`). Edit
tokens only in `ss-tokens.css`.

Django global CSS (non-React) is a barrel at `static/css/style.css` that
`@import`s domain files (`tokens`, `bootstrap-theme`, `chrome`, `map-scene`,
`auth`, `legacy`). See the manager-ui skill.

Set `SKIP_UI=1` to skip the UI build when running `make -C manager build-image`
offline without Node (token sync still runs).

Built JS/CSS under `static/ui/` get SPDX license headers from the Vite
`writeBundle` plugin (esbuild minify strips Rollup banners). These are local
build outputs and are not tracked in Git.

## Django load path

Each page mounts a root and loads the matching
`{% static 'ui/<entry>.js' %}` as `type="module"`. Islands load bootstrap from
`GET /api/v1/ui-bootstrap/?page=…` (optional embedded `json_script` still
works for tests / static smoke).

Scene detail also adopts `#ss-map-host`; control tab panels are React-owned
inside `SceneSidePanel` (hard-contract pane ids `#cameras`, `#trips`, …).
ROI/tripwire editor cards portal into `#roi-fields` / `#tripwire-fields`.
Sheets open from `?ss=<action>&id=<optional>` (see `src/lib/sheetQuery.ts`).

## Static host (plan item F)

Build emits `static/ui/shell.html` + `spa.js`. Point a reverse proxy so that:

- `/` , `/<scene-uuid>/`, `/cam/list/`, `/singleton_sensor/list/`,
  `/asset/list/`, `/model/list/` serve `shell.html` (or redirect to
  `/static/ui/shell.html` with path preserved via `try_files`)
- `/sign_in/` may serve `sign-in.html` (or Django thin mount + `sign-in.js`)
- `/static/` → Manager static files (css, js, ui, assets, images, bootstrap)
- `/api/`, `/media/`, `/sign_in/` (POST), `/sign_out/`, `/mqtt` → API / session host

Chrome, scenes, scene detail, and list pages (cameras / sensors / assets /
models / list-sheets) bootstraps come from
`GET /api/v1/ui-bootstrap/?page=…` (session cookie or Token). Django page
templates remain thin mounts (root + script tags) until a static host cutover.

## Lint

```bash
npm run lint
npm run typecheck
```
