// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider, useAppToast, installLegacyToastBridge } from "./components/ToastProvider";
import { useSheetFromQuery } from "./hooks/useSheetFromQuery";
import { CameraSheet } from "./sheets/CameraSheet";
import { SensorSheet } from "./sheets/SensorSheet";
import { AssetSheet } from "./sheets/AssetSheet";
import { EmbedFormOverlay, embedFormUrl } from "./sheets/EmbedFormOverlay";
import type { SheetAction } from "./lib/sheetQuery";
import "./tokens/tokens.css";

type ListBootstrap = {
  authToken: string;
  isSuperuser: boolean;
  kind: "cam" | "sensor" | "asset";
  defaultSceneId?: string | null;
  scenes?: { id: string; name: string }[];
};

function isAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v);
}

function ListSheetsApp({ bootstrap }: { bootstrap: ListBootstrap }) {
  const { sheet, open, close } = useSheetFromQuery();
  const toast = useAppToast();
  useEffect(() => installLegacyToastBridge(toast), [toast]);

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
      if (ss && isAction(ss)) {
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
      const camEdit = url.pathname.match(/\/cam\/update\/(\d+)/);
      if (camEdit) {
        ev.preventDefault();
        open("cam-edit", camEdit[1]);
      }
      const sensorEdit = url.pathname.match(
        /\/singleton_sensor\/update\/(\d+)/,
      );
      if (sensorEdit) {
        ev.preventDefault();
        open("sensor-edit", sensorEdit[1]);
      }
      const assetEdit = url.pathname.match(/\/asset\/update\/(\d+)/);
      if (assetEdit) {
        ev.preventDefault();
        open("asset-edit", assetEdit[1]);
      }
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [open, bootstrap.kind]);

  const reload = () => window.location.reload();
  const sceneId = bootstrap.defaultSceneId || "";
  const scenes = bootstrap.scenes || [];

  if (!bootstrap.isSuperuser) {
    return null;
  }

  const editSrc =
    sheet.action === "cam-edit" && sheet.id
      ? embedFormUrl(`/cam/update/${sheet.id}/`)
      : sheet.action === "sensor-edit" && sheet.id
        ? embedFormUrl(`/singleton_sensor/update/${sheet.id}/`)
        : sheet.action === "asset-edit" && sheet.id
          ? embedFormUrl(`/asset/update/${sheet.id}/`)
          : null;

  const editTitle =
    sheet.action === "cam-edit"
      ? "Edit camera"
      : sheet.action === "sensor-edit"
        ? "Edit sensor"
        : sheet.action === "asset-edit"
          ? "Edit asset"
          : "Edit";

  return (
    <>
      {bootstrap.kind === "cam" && (
        <CameraSheet
          open={sheet.action === "cam-create"}
          mode="create"
          sceneId={sceneId}
          scenes={scenes}
          authToken={bootstrap.authToken}
          onClose={close}
          onSaved={reload}
        />
      )}
      {bootstrap.kind === "sensor" && (
        <SensorSheet
          open={sheet.action === "sensor-create"}
          mode="create"
          sceneId={sceneId}
          scenes={scenes}
          authToken={bootstrap.authToken}
          onClose={close}
          onSaved={reload}
        />
      )}
      {bootstrap.kind === "asset" && (
        <AssetSheet
          open={sheet.action === "asset-create"}
          mode="create"
          authToken={bootstrap.authToken}
          onClose={close}
          onSaved={reload}
        />
      )}
      <EmbedFormOverlay
        open={Boolean(editSrc)}
        src={editSrc}
        title={editTitle}
        onClose={close}
      />
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
        <ListSheetsApp bootstrap={bootstrap} />
      </ToastProvider>
    </StrictMode>,
  );
}
