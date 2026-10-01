<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ADR 19: Host-Independent Manager UI (React Islands + Bootstrap Contract)

- **Author(s)**: [Sarat Poluri](https://github.com/spoluri)
- **Date**: 2026-10-01
- **Status**: `Proposed`

## Context

The Manager 2D UI was rewritten as React islands under `manager/frontend/`, but
pages still assumed Django template DOM, CSRF session POSTs, and ad-hoc
`window.ss*` bridges. That bound the UI to Django’s request cycle and blocked a
future API-only host.

Operators also needed a path that works without embedding `json_script`
bootstraps on every page (static `shell.html`, Kubernetes / compose demos). A
full framework swap (e.g. FastAPI) and a React replacement for
`scenescape3d.js` remain optional and out of scope for this decision.

## Decision

1. **Freeze a portable UI↔backend contract** in
   [`docs/design/manager-ui-backend-contract.md`](../design/manager-ui-backend-contract.md):
   island bootstrap shapes, Token `/api/v1` REST the islands call, auth modes,
   and MQTT topic families. Hard DOM / `window.ss*` bridges are transitional
   debt, not the long-term boundary.

2. **Serve host-independent UI** via `GET /api/v1/ui-bootstrap/?page=…`
   (Session or Token) plus static shells (`static/ui/shell.html` + `spa.js`,
   `sign-in.html` + `sign-in.js`). Islands prefer embedded bootstrap when
   present, otherwise fetch the API and persist `authToken` for subsequent
   Token REST.

3. **Keep thin optional Django mounts** as a dual path: templates may still
   provide roots + scripts, but they are not required when the static shell is
   used. Camera calibrate embeds continue to load legacy `sscape.js` (chrome
   skipped).

4. **Move runtime ownership into React** for scene MQTT connect, camera strip,
   local sensors, chrome, sign-in, and live marks on React-map scenes. Snap /
   `sscape.js` remain for child ROI / tripwire / sensor overlays and calibrate;
   refreshable `scene_id` supports late DOM creation in the static shell.

5. **Port destructive and setup APIs to Token auth**: entity deletes,
   model-directory, and mesh generate/status (`MeshGenerationRequest`
   idempotency per mapping `request_id`). Domain helpers (e.g. scene map
   align/thumbnail) live outside serializers/views.

6. **Defer framework swap and full React 3D viewport** — same frozen contract;
   cut Django templates or rewrite `scenescape3d.js` only when operators run on
   the static path and a dedicated 3D epic is scheduled ([ADR 18](./0018-3d-child-scene-placement.md)
   already shipped a thin placement widget).

Layout, tokens, and remaining hard DOM contracts stay in
[`.github/skills/manager-ui/SKILL.md`](../../.github/skills/manager-ui/SKILL.md).

## Alternatives Considered

- **Keep Django templates as the only host** — simpler short term; blocks
  static/API-only deploys and keeps CSRF dual paths. Rejected for the
  swappable-host goal.
- **Big-bang FastAPI / SPA rewrite** — high risk while islands still need Snap
  calibrate and mesh flows. Deferred; contract-first path chosen instead.
- **Leave MQTT / camera strip in `sscape.js`** — fewer React changes, but
  status, decode, and teardown bugs stayed in hybrid globals. Rejected for
  scene-detail ownership.

## Consequences

### Positive

- Manager UI can load from a static shell against any host that implements the
  frozen bootstrap + Token REST + MQTT contract.
- Django remains a valid dual path without blocking host independence.
- Mesh finalize and models directory no longer depend on CSRF session quirks.
- Future framework or 3D work has a documented boundary.

### Negative

- Dual path (Django thin mounts vs static shell) must stay behaviorally aligned
  until templates are dropped.
- Snap / calibrate still own some MQTT and THREE surfaces; `window.ss*` is not
  fully gone.
- Scene side panel overlays the full-bleed map (Hide panel to edit geometry
  underneath) — intentional UX trade-off.

## References

- [Manager UI backend contract](../design/manager-ui-backend-contract.md)
- [Manager UI skill](../../.github/skills/manager-ui/SKILL.md)
- [Manager frontend README](../../manager/frontend/README.md)
- [ADR 17: Geospatial Child-Scene Linking](./0017-geospatial-child-scene-linking.md)
- [ADR 18: 3D Child-Scene Placement](./0018-3d-child-scene-placement.md)
