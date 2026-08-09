// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect } from "react";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import type { SheetAction } from "../lib/sheetQuery";
import { CameraSheet } from "./CameraSheet";
import { SensorSheet } from "./SensorSheet";
import { ChildSheet, type SceneOption } from "./ChildSheet";
import { CalibrateOverlay } from "./CalibrateOverlay";

type Props = {
  sceneId: string;
  authToken: string;
  isSuperuser: boolean;
  scenes: SceneOption[];
};

/** Same-page sheet/overlay actions hosted on the scene workspace. */
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
 * Intercepts same-page ?ss= create/calibrate/manage links; hosts drawers + overlays.
 */
export function SceneWorkspaceSheets({
  sceneId,
  authToken,
  isSuperuser,
  scenes,
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

  if (!isSuperuser) {
    return null;
  }

  const action = sheet.action;

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
      <CalibrateOverlay
        open={action === "calibrate-cam" || action === "calibrate-sensor"}
        kind={action === "calibrate-sensor" ? "sensor" : "cam"}
        entityPk={sheet.id || ""}
        onClose={close}
      />
      <CalibrateOverlay
        open={action === "scene-manage"}
        kind="scene"
        entityPk={sceneId}
        onClose={close}
      />
    </>
  );
}
