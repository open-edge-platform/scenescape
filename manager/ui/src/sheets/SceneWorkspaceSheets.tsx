// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo } from "react";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import type { SheetAction } from "../lib/sheetQuery";
import type { SceneCameraBootstrap } from "../scene/types";
import { CameraSheet } from "./CameraSheet";
import { SensorSheet } from "./SensorSheet";
import { ChildSheet, type SceneOption } from "./ChildSheet";
import { SceneManagePanel } from "./SceneManagePanel";
import { CameraCalibratePanel } from "./CameraCalibratePanel";
import { SensorCalibratePanel } from "./SensorCalibratePanel";

/**
 * Command surfaces: create sheets use Drawer (`chooseCommandSurface("simple")`);
 * manage/calibrate use WorkspacePanel (`chooseCommandSurface("complex")`).
 */

type Props = {
  sceneId: string;
  authToken: string;
  isSuperuser: boolean;
  isKubernetes: boolean;
  scenes: SceneOption[];
  cameras: SceneCameraBootstrap[];
};

/** Same-page sheet/panel actions hosted on the scene workspace. */
const WORKSPACE_ACTIONS = new Set([
  "cam-create",
  "sensor-create",
  "child-create",
  "calibrate-cam",
  "calibrate-sensor",
  "scene-manage",
]);

function isWorkspaceAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v && WORKSPACE_ACTIONS.has(v));
}

/**
 * Intercepts same-page ?ss= create/calibrate/manage links; hosts drawers +
 * full-viewport React workspace panels (no Django iframe chrome).
 */
export function SceneWorkspaceSheets({
  sceneId,
  authToken,
  isSuperuser,
  isKubernetes,
  scenes,
  cameras,
}: Props) {
  const { sheet, open, close } = useSheetFromQuery();

  useEffect(() => {
    const onClick = (ev: Event) => {
      const target = ev.target as HTMLElement | null;
      if (!target) {
        return;
      }
      const link = target.closest("a[href]") as HTMLAnchorElement | null;
      if (!link?.href) {
        return;
      }
      let url: URL;
      try {
        url = new URL(link.href, window.location.origin);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) {
        return;
      }
      const ss = url.searchParams.get("ss");
      if (!ss || !isWorkspaceAction(ss)) {
        return;
      }
      if (
        url.pathname === window.location.pathname ||
        url.pathname === `/${sceneId}/` ||
        url.pathname === `/${sceneId}`
      ) {
        ev.preventDefault();
        ev.stopPropagation();
        open(ss, url.searchParams.get("id"));
      }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [open, sceneId]);

  const reload = useCallback(() => {
    window.location.reload();
  }, []);

  const camByPk = useMemo(() => {
    const map = new Map<string, SceneCameraBootstrap>();
    cameras.forEach((c) => map.set(String(c.id), c));
    return map;
  }, [cameras]);

  if (!isSuperuser) {
    return null;
  }

  const action = sheet.action;
  const calibrateCam =
    action === "calibrate-cam" && sheet.id
      ? camByPk.get(String(sheet.id))
      : null;

  return (
    <>
      <CameraSheet
        open={action === "cam-create"}
        mode="create"
        sceneId={sceneId}
        scenes={scenes}
        authToken={authToken}
        onClose={close}
        onSaved={reload}
      />
      <SensorSheet
        open={action === "sensor-create"}
        mode="create"
        sceneId={sceneId}
        scenes={scenes}
        authToken={authToken}
        onClose={close}
        onSaved={reload}
      />
      <ChildSheet
        open={action === "child-create"}
        mode="create"
        parentSceneId={sceneId}
        scenes={scenes}
        authToken={authToken}
        onClose={close}
        onSaved={reload}
      />
      <SceneManagePanel
        open={action === "scene-manage"}
        sceneId={sceneId}
        authToken={authToken}
        onClose={close}
        onSaved={reload}
      />
      <CameraCalibratePanel
        open={Boolean(calibrateCam)}
        cameraPk={calibrateCam?.id || ""}
        sensorId={calibrateCam?.sensorId || ""}
        sceneId={sceneId}
        authToken={authToken}
        isKubernetes={isKubernetes}
        onClose={close}
        onSaved={reload}
      />
      <SensorCalibratePanel
        open={action === "calibrate-sensor"}
        sensorPk={sheet.id || ""}
        onClose={close}
        onSaved={reload}
      />
    </>
  );
}
