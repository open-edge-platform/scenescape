// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Legacy Snap.svg map host — required DOM ids for sscape.js.
 * React only owns layout chrome around this host; do not remount #map/#svgout.
 */
export const LEGACY_MAP_IDS = {
  host: "ss-map-host",
  map: "map",
  svgout: "svgout",
  mapControls: "map-controls",
  fullscreen: "fullscreen",
  scale: "scale",
  scene: "scene",
} as const;

export function notifyMapHostReady(): void {
  window.dispatchEvent(new CustomEvent("ss-map-host-ready"));
  if (typeof window.fitSceneMapDisplay === "function") {
    window.fitSceneMapDisplay();
  }
}
