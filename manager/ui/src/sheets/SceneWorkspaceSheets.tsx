// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo } from "react";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import { activateSceneTab, tabForSheetAction } from "../lib/sceneTab";
import type { SheetAction } from "../lib/sheetQuery";
import type { SceneCameraBootstrap, SceneSensorBootstrap } from "../scene/types";
import { CameraSheet } from "./CameraSheet";
import { SensorSheet } from "./SensorSheet";
import { ChildSheet, type SceneOption } from "./ChildSheet";
import { SceneManagePanel } from "./SceneManagePanel";
import { CameraCalibratePanel } from "./CameraCalibratePanel";
import { SensorCalibratePanel } from "./SensorCalibratePanel";

/**
 * Command surfaces: create/edit/manage sheets use Drawer; calibrate uses
 * WorkspacePanel.
 */

type Props = {
  sceneId: string;
  authToken: string;
  isSuperuser: boolean;
  isKubernetes: boolean;
  scenes: SceneOption[];
  cameras: SceneCameraBootstrap[];
  sensors?: SceneSensorBootstrap[];
  mapUrl?: string | null;
  mapScale?: number | null;
};

const WORKSPACE_ACTIONS = new Set([
  "cam-create",
  "cam-edit",
  "sensor-create",
  "sensor-edit",
  "child-create",
  "child-edit",
  "calibrate-cam",
  "calibrate-sensor",
  "scene-manage",
]);

function isWorkspaceAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v && WORKSPACE_ACTIONS.has(v));
}

/**
 * Intercepts same-page ?ss= create/edit/calibrate/manage links; hosts drawers +
 * full-viewport React workspace panels.
 */
export function SceneWorkspaceSheets({
  sceneId,
  authToken,
  isSuperuser,
  isKubernetes,
  scenes,
  cameras,
  sensors = [],
  mapUrl = null,
  mapScale = null,
}: Props) {
  const { sheet, open, close } = useSheetFromQuery();

  const openSheet = useCallback(
    (action: Exclude<SheetAction, null>, id: string | null = null) => {
      const tab = tabForSheetAction(action);
      if (tab) {
        activateSceneTab(tab);
      }
      open(action, id);
    },
    [open],
  );

  const closeSheet = useCallback(() => {
    const tab = tabForSheetAction(sheet.action);
    close();
    if (tab) {
      activateSceneTab(tab);
    }
  }, [close, sheet.action]);

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
        openSheet(ss, url.searchParams.get("id"));
      }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [openSheet, sceneId]);

  useEffect(() => {
    const tab = tabForSheetAction(sheet.action);
    if (tab) {
      activateSceneTab(tab);
    }
  }, [sheet.action]);

  const reload = useCallback(() => {
    window.location.reload();
  }, []);

  const camByPk = useMemo(() => {
    const map = new Map<string, SceneCameraBootstrap>();
    cameras.forEach((c) => map.set(String(c.id), c));
    return map;
  }, [cameras]);

  const camBySensorId = useMemo(() => {
    const map = new Map<string, SceneCameraBootstrap>();
    cameras.forEach((c) => map.set(String(c.sensorId), c));
    return map;
  }, [cameras]);

  const sensorByPk = useMemo(() => {
    const map = new Map<string, SceneSensorBootstrap>();
    sensors.forEach((s) => map.set(String(s.id), s));
    return map;
  }, [sensors]);

  if (!isSuperuser) {
    return null;
  }

  const action = sheet.action;
  const calibrateCam =
    action === "calibrate-cam" && sheet.id
      ? camByPk.get(String(sheet.id))
      : null;
  const calibrateSensor =
    action === "calibrate-sensor" && sheet.id
      ? sensorByPk.get(String(sheet.id))
      : null;

  const camEditUid =
    action === "cam-edit" && sheet.id
      ? camBySensorId.get(String(sheet.id))?.sensorId || String(sheet.id)
      : null;

  return (
    <>
      <CameraSheet
        open={action === "cam-create" || action === "cam-edit"}
        mode={action === "cam-edit" ? "edit" : "create"}
        sceneId={sceneId}
        scenes={scenes}
        sensorUid={action === "cam-edit" ? camEditUid : null}
        authToken={authToken}
        onClose={closeSheet}
        onSaved={reload}
      />
      <SensorSheet
        open={action === "sensor-create" || action === "sensor-edit"}
        mode={action === "sensor-edit" ? "edit" : "create"}
        sceneId={sceneId}
        scenes={scenes}
        sensorUid={action === "sensor-edit" ? sheet.id : null}
        authToken={authToken}
        onClose={closeSheet}
        onSaved={reload}
      />
      <ChildSheet
        open={action === "child-create" || action === "child-edit"}
        mode={action === "child-edit" ? "edit" : "create"}
        parentSceneId={sceneId}
        childUid={action === "child-edit" ? sheet.id : null}
        scenes={scenes}
        authToken={authToken}
        onClose={closeSheet}
        onSaved={reload}
      />
      <SceneManagePanel
        open={action === "scene-manage"}
        sceneId={sceneId}
        authToken={authToken}
        onClose={closeSheet}
        onSaved={reload}
      />
      <CameraCalibratePanel
        open={Boolean(calibrateCam)}
        cameraPk={calibrateCam?.id || ""}
        sensorId={calibrateCam?.sensorId || ""}
        cameraName={calibrateCam?.name || ""}
        sceneId={sceneId}
        authToken={authToken}
        isKubernetes={isKubernetes}
        onClose={closeSheet}
        onSaved={reload}
      />
      <SensorCalibratePanel
        open={Boolean(calibrateSensor) || action === "calibrate-sensor"}
        sensorPk={calibrateSensor?.id || sheet.id || ""}
        sensorId={calibrateSensor?.sensorId || ""}
        sceneId={sceneId}
        authToken={authToken}
        mapUrlHint={mapUrl}
        mapScale={mapScale}
        onClose={closeSheet}
        onSaved={reload}
      />
    </>
  );
}
