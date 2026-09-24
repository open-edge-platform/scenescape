// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode, useEffect, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider } from "./components/ToastProvider";
import { LegacyConfirmHost } from "./components/LegacyConfirmHost";
import { useSheetFromQuery } from "./hooks/useSheetFromQuery";
import { CameraSheet } from "./sheets/CameraSheet";
import { SensorSheet } from "./sheets/SensorSheet";
import { AssetSheet } from "./sheets/AssetSheet";
import { CameraCalibratePanel } from "./sheets/CameraCalibratePanel";
import { SensorCalibratePanel } from "./sheets/SensorCalibratePanel";
import type { SheetAction } from "./lib/sheetQuery";
import "./tokens/tokens.css";

type ListEntity = {
  id: string;
  sensorId: string;
  name: string;
  sceneId?: string | null;
};

type ListBootstrap = {
  authToken: string;
  isSuperuser: boolean;
  kind: "cam" | "sensor" | "asset";
  defaultSceneId?: string | null;
  isKubernetes?: boolean;
  cameras?: ListEntity[];
  sensors?: ListEntity[];
  scenes?: { id: string; name: string }[];
};

const SHEET_ACTIONS = new Set([
  "cam-create",
  "cam-edit",
  "sensor-create",
  "sensor-edit",
  "asset-create",
  "asset-edit",
  "calibrate-cam",
  "calibrate-sensor",
]);

function isSheetAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v && SHEET_ACTIONS.has(v));
}

function ListSheetsApp({ bootstrap }: { bootstrap: ListBootstrap }) {
  const { sheet, open, close } = useSheetFromQuery();

  useEffect(() => {
    const onClick = (ev: Event) => {
      const link = (ev.target as HTMLElement | null)?.closest(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (!link?.href) {
        return;
      }
      let url: URL;
      try {
        url = new URL(link.href, window.location.origin);
      } catch {
        return;
      }
      const ss = url.searchParams.get("ss");
      if (ss && isSheetAction(ss)) {
        ev.preventDefault();
        open(ss, url.searchParams.get("id"));
        return;
      }
      if (link.id === "new-camera" || link.id === "new-sensor") {
        ev.preventDefault();
        open(bootstrap.kind === "sensor" ? "sensor-create" : "cam-create");
      }
      if (link.id === "new-asset" || /\/asset\/create\/?$/.test(url.pathname)) {
        ev.preventDefault();
        open("asset-create");
      }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [open, bootstrap.kind]);

  const reload = () => window.location.reload();
  const sceneId = bootstrap.defaultSceneId || "";
  const scenes = bootstrap.scenes || [];
  const action = sheet.action;
  const isKubernetes = Boolean(bootstrap.isKubernetes);

  const camByPk = useMemo(() => {
    const map = new Map<string, ListEntity>();
    (bootstrap.cameras || []).forEach((c) => map.set(String(c.id), c));
    return map;
  }, [bootstrap.cameras]);

  const sensorByPk = useMemo(() => {
    const map = new Map<string, ListEntity>();
    (bootstrap.sensors || []).forEach((s) => map.set(String(s.id), s));
    return map;
  }, [bootstrap.sensors]);

  const calibrateCam =
    action === "calibrate-cam" && sheet.id
      ? camByPk.get(String(sheet.id))
      : null;
  const calibrateSensor =
    action === "calibrate-sensor" && sheet.id
      ? sensorByPk.get(String(sheet.id))
      : null;

  if (!bootstrap.isSuperuser) {
    return null;
  }

  return (
    <>
      {bootstrap.kind === "cam" && (
        <>
          <CameraSheet
            open={action === "cam-create" || action === "cam-edit"}
            mode={action === "cam-edit" ? "edit" : "create"}
            sceneId={sceneId}
            scenes={scenes}
            sensorUid={action === "cam-edit" ? sheet.id : null}
            authToken={bootstrap.authToken}
            onClose={close}
            onSaved={reload}
          />
          <CameraCalibratePanel
            open={Boolean(calibrateCam)}
            cameraPk={calibrateCam?.id || ""}
            sensorId={calibrateCam?.sensorId || ""}
            cameraName={calibrateCam?.name || ""}
            sceneId={calibrateCam?.sceneId || sceneId || ""}
            authToken={bootstrap.authToken}
            isKubernetes={isKubernetes}
            onClose={close}
            onSaved={reload}
          />
        </>
      )}
      {bootstrap.kind === "sensor" && (
        <>
          <SensorSheet
            open={action === "sensor-create" || action === "sensor-edit"}
            mode={action === "sensor-edit" ? "edit" : "create"}
            sceneId={sceneId}
            scenes={scenes}
            sensorUid={action === "sensor-edit" ? sheet.id : null}
            authToken={bootstrap.authToken}
            onClose={close}
            onSaved={reload}
          />
          <SensorCalibratePanel
            open={Boolean(calibrateSensor)}
            sensorPk={calibrateSensor?.id || ""}
            sensorId={calibrateSensor?.sensorId || ""}
            sceneId={calibrateSensor?.sceneId || sceneId || ""}
            authToken={bootstrap.authToken}
            onClose={close}
            onSaved={reload}
          />
        </>
      )}
      {bootstrap.kind === "asset" && (
        <AssetSheet
          open={action === "asset-create" || action === "asset-edit"}
          mode={action === "asset-edit" ? "edit" : "create"}
          assetUid={action === "asset-edit" ? sheet.id : null}
          authToken={bootstrap.authToken}
          onClose={close}
          onSaved={reload}
        />
      )}
    </>
  );
}

function readBootstrap(): ListBootstrap | null {
  const el = document.getElementById("ss-list-sheets-bootstrap");
  if (!el?.textContent) {
    return null;
  }
  try {
    return JSON.parse(el.textContent) as ListBootstrap;
  } catch {
    return null;
  }
}

const bootstrap = readBootstrap();
if (bootstrap) {
  const host = document.createElement("div");
  host.id = "ss-list-sheets-root";
  document.body.appendChild(host);
  createRoot(host).render(
    <StrictMode>
      <ToastProvider>
        <LegacyConfirmHost>
          <ListSheetsApp bootstrap={bootstrap} />
        </LegacyConfirmHost>
      </ToastProvider>
    </StrictMode>,
  );
}
