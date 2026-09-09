<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI (React island)

Vite + React + TypeScript package that builds Manager 2D islands into Django
static assets.

Status of shipped work vs remaining empty-space / 3D epics:
[`.github/plans/manager-ui.md`](../../.github/plans/manager-ui.md).

## Setup

```bash
cd manager/ui
npm ci
```

## Build

```bash
npm run build
# or from repo:
make -C manager ui-build
```

Outputs under `manager/src/manager/static/ui/`:

| Entry                 | Files                    | Used by                           |
| --------------------- | ------------------------ | --------------------------------- |
| shared CSS            | `manager-ui.css`         | All islands                       |
| `scene-detail`        | `scene-detail.js`        | Scene detail                      |
| `scenes-home`         | `scenes-home.js`         | Scenes gallery                    |
| `list-sheets`         | `list-sheets.js`         | Cam / sensor / asset lists        |
| `admin-list`          | `admin-list.js`          | Camera / sensor list chrome       |
| `destructive-actions` | `destructive-actions.js` | In-page delete confirms           |
| `models-directory`    | `models-directory.js`    | K8s Models page (browse / upload) |

Set `SKIP_UI=1` to skip the UI build when running `make -C manager build-image`
offline without Node.

## Django load path

Each page mounts a root + `json_script` bootstrap and loads the matching
`{% static 'ui/<entry>.js' %}` as `type="module"`.

Scene detail also adopts `#ss-map-host` and `#scene-detail-panels`; ROI/tripwire
editor cards are React-owned via `#roi-fields` / `#tripwire-fields`. Sheets open
from `?ss=<action>&id=<optional>` (see `src/lib/sheetQuery.ts`).

## Lint

```bash
npm run lint
npm run typecheck
```
