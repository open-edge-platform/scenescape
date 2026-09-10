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

## 2. Optional: how-to updates

When chrome labels, open paths, or nav targets change, update
`docs/user-guide/how-to-guides/` (see
[`.github/skills/documentation-how/SKILL.md`](../skills/documentation-how/SKILL.md)).
