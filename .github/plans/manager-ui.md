<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Manager UI

Remaining work after the 2D React rewrite.

Conventions, layout shells, tokens, and hard DOM contracts:
[`.github/skills/manager-ui/SKILL.md`](../skills/manager-ui/SKILL.md).
Package notes: [`manager/frontend/README.md`](../../manager/frontend/README.md).

## 1. 3D scene viewport (epic)

**Not started.** Legacy Three.js surface remains:

- Entry: `manager/backend/manager/static/js/scenescape3d.js` plus modules under
  `static/js/thing/`, `viewport.js`, managers, etc.
- Mount: `base_3d.html` — no React root / no `manager/frontend` 3D entry.
- Scene detail links out (`#3d-view` → `urls.scene3d`). 3D chrome already
  deep-links back to 2D (`#scene-detail-link`, `#scene-detail-button`,
  per-camera calibrate URLs).

Replace or wrap with a React-owned shell that reuses MQTT / auth patterns
from the 2D rewrite. Keep the **workspace** shell (full-bleed). Do **not**
fold into 2D trickle PRs.

Suggested slices:

1. Inventory: entry points, MQTT topics, asset load path, Django mounts.
2. Thin React mount + bootstrap JSON (parity shell; keep Three under the hood).
3. Port interaction chrome (layers, selection, camera controls) into React.
4. Retire legacy script load path when UI tests cover 3D BAT.

Gate: document any new 3D contract ids in the manager-ui skill before deleting
legacy globals; UI BAT green for scene 3D view when that suite exists.

## 2. Path to a swappable backend (epic)

**Status:** Moderately positioned for a gradual API-backed frontend — **not**
ready for a clean Django drop-in replacement.

The React islands already prefer REST + bootstrap JSON (`authToken`, scene
payloads) over pure server-rendered forms. That is the right direction: grow
the UI against a documented HTTP/MQTT contract, then put a different server
behind that contract. Swapping Django today would still be a cut-over of host
+ API + auth + realtime, not just an ORM change.

### What already helps

- Vite islands (`scenes-home`, `scene-detail`, admin lists, sheets) own more
  chrome each release.
- Bootstrap `json_script` + REST tokens reduce template form coupling.
- MQTT and auth patterns are reusable if the wire contract is frozen.

### What still binds us to Django

- Page shells, session/auth, and static serving still come from Django
  templates (`base.html`, `sceneDetail.html`, list pages, etc.).
- Hard DOM/window contracts (`#map-controls`, `#ss-map-host`, `window.ss*`,
  legacy map JS) couple React to Django-rendered markup and lifecycle — not
  to a stable API alone. See the manager-ui skill hard-contract tables.
- Domain logic (scene map/GLB upload, serializers, permissions, MQTT wiring)
  lives in Django models/views without a backend-agnostic service boundary.
- Dual-run leftovers (map parking, Bootstrap widgets, mixed CSS barrels)
  keep the UI host tied to the Django request cycle.

### Suggested slices (order matters)

1. **Freeze the contract.** Document REST + MQTT + bootstrap JSON shapes the
   UI actually needs (auth, scenes, cameras/sensors, map assets, delete
   impact). Treat skill hard contracts as debt to retire, not as the long-term
   boundary.
2. **Retire template/DOM coupling.** Move remaining Django-owned chrome
   (map toggles parking, nav/about host, list shells) into React mounts so
   islands boot from bootstrap + fetch only — no required sibling DOM from
   Django templates beyond a single root.
3. **Auth as a portable session.** Abstract login/CSRF/token issuance behind
   the same client helpers the islands already use; stop assuming Django
   session cookies in new code.
4. **Extract domain behind HTTP.** Scene map upload/align/thumbnail, CRUD,
   and permissions callable without importing Django models from the UI path.
   Prefer thin API handlers over template views for anything the React app
   touches.
5. **Host independence last.** Only after (1)–(4): serve the SPA/static UI
   from a non-Django host (or reverse proxy) pointed at the API. Do **not**
   attempt a framework swap before the UI can run without template-injected
   DOM and `window.ss*` bridges.

Gate: UI BAT and manager functional tests green against the frozen contract;
hard-contract table in the manager-ui skill shrinks as IDs move behind React
ownership; no new `window.ss*` or Django-only DOM requirements for new UI.

Out of scope for trickle PRs: rewriting the tracker/controller stack, or
replacing Django in one shot.

## 3. Optional: how-to updates

When chrome labels, open paths, or nav targets change, update
`docs/user-guide/how-to-guides/` (see
[`.github/skills/documentation-how/SKILL.md`](../skills/documentation-how/SKILL.md)).
