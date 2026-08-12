// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Scene detail control-tab ids shared by sheets and the side panel. */
export type SceneControlTabId =
  | "cameras"
  | "sensors"
  | "regions"
  | "tripwires"
  | "children"
  | "mqtt";

const STORAGE_PREFIX = "ss-scene-tab:";
export const SCENE_TAB_EVENT = "ss-scene-tab";

const TAB_BY_SHEET: Record<string, SceneControlTabId> = {
  "cam-create": "cameras",
  "cam-edit": "cameras",
  "calibrate-cam": "cameras",
  "sensor-create": "sensors",
  "sensor-edit": "sensors",
  "calibrate-sensor": "sensors",
  "child-create": "children",
  "child-edit": "children",
};

export function tabForSheetAction(
  action: string | null | undefined,
): SceneControlTabId | null {
  if (!action) {
    return null;
  }
  return TAB_BY_SHEET[action] || null;
}

export function readStoredSceneTab(
  sceneId: string,
  fallback: SceneControlTabId = "cameras",
): SceneControlTabId {
  if (!sceneId || typeof sessionStorage === "undefined") {
    return fallback;
  }
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + sceneId);
    if (
      raw === "cameras" ||
      raw === "sensors" ||
      raw === "regions" ||
      raw === "tripwires" ||
      raw === "children" ||
      raw === "mqtt"
    ) {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return fallback;
}

export function writeStoredSceneTab(
  sceneId: string,
  tabId: SceneControlTabId,
): void {
  if (!sceneId || typeof sessionStorage === "undefined") {
    return;
  }
  try {
    sessionStorage.setItem(STORAGE_PREFIX + sceneId, tabId);
  } catch {
    /* ignore */
  }
}

/** Ask the scene side panel to show a tab (and persist it). */
export function activateSceneTab(tabId: SceneControlTabId): void {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(SCENE_TAB_EVENT, { detail: { tabId } }),
  );
}
