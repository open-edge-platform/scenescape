<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Follow-on F2 — 3D scene viewport (epic)

Scheduled after Manager 2D Phases 0–5. Do **not** fold into 2D trickle PRs.

## Scope

Replace or wrap the legacy Three.js scene surface (~4.3k LOC in
`scenescape3d.js` and related assets) with a React-owned shell that reuses
MQTT / auth patterns clarified by the 2D rewrite.

## Why separate

- Different product surface from 2D map config (ROI / tripwire / calibrate).
- Heavy WebGL / asset-loading concerns; different test strategy.
- Shared patterns (tokens, sheets, REST) should stabilize first.

## Suggested slices

1. Inventory: entry points, MQTT topics, asset load path, Django template mounts.
2. Thin React mount + bootstrap JSON (parity shell; keep Three under the hood).
3. Port interaction chrome (layers, selection, camera controls) into React.
4. Retire legacy script load path when UI tests cover 3D BAT.

## Non-goals (this epic’s kickoff)

- Rewriting model-directory (see F1).
- Reopening Snap / calibrate iframe work.

## Gate

Document contract ids for 3D in `.github/plans/` before deleting legacy
globals; UI BAT green for scene 3D view when that suite exists.
