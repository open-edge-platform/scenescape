// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect } from "react";
import { useSheetFromQuery } from "../hooks/useSheetFromQuery";
import type { SheetAction } from "../lib/sheetQuery";
import { CameraSheet } from "./CameraSheet";
import { SensorSheet } from "./SensorSheet";
import { ChildSheet, type SceneOption } from "./ChildSheet";
import { CalibrateOverlay } from "./CalibrateOverlay";
import { EmbedFormOverlay, embedFormUrl } from "./EmbedFormOverlay";

type Props = {
  sceneId: string;
  authToken: string;
  isSuperuser: boolean;
  scenes: SceneOption[];
};

function isAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v);
}

function editOverlay(
  action: SheetAction,
  id: string | null,
): { src: string; title: string } | null {
  if (!id) {
    return null;
  }
  switch (action) {
    case "scene-edit":
      return {
        src: embedFormUrl(`/scene/update/${id}/`),
        title: "Edit scene",
      };
    case "cam-edit":
      return {
        src: embedFormUrl(`/cam/update/${id}/`),
        title: "Edit camera",
      };
    case "sensor-edit":
      return {
        src: embedFormUrl(`/singleton_sensor/update/${id}/`),
        title: "Edit sensor",
      };
    case "child-edit":
      return {
        src: embedFormUrl(`/child/update/${id}/`),
        title: "Edit child link",
      };
    default:
      return null;
  }
}

/**
 * Intercepts same-page ?ss= links and hosts create drawers + edit/calibrate overlays.
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
      if (!ss) {
        return;
      }
      if (
        url.pathname === window.location.pathname ||
        url.pathname === `/${sceneId}/` ||
        url.pathname === `/${sceneId}`
      ) {
        if (!isAction(ss)) {
          return;
        }
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
  const edit = editOverlay(action, sheet.id);

  return (
    <>
      <CameraSheet
        open={action === "cam-create"}
        mode="create"
        sceneId={sceneId}
        authToken={authToken}
        onClose={close}
        onSaved={reload}
      />
      <SensorSheet
        open={action === "sensor-create"}
        mode="create"
        sceneId={sceneId}
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
      <EmbedFormOverlay
        open={Boolean(edit)}
        src={edit?.src || null}
        title={edit?.title || "Edit"}
        onClose={close}
      />
      <CalibrateOverlay
        open={action === "calibrate-cam" || action === "calibrate-sensor"}
        kind={action === "calibrate-sensor" ? "sensor" : "cam"}
        entityPk={sheet.id || ""}
        onClose={close}
      />
    </>
  );
}
