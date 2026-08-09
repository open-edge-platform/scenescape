// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider } from "./components/ToastProvider";
import { LegacyConfirmHost } from "./components/LegacyConfirmHost";
import { useSheetFromQuery } from "./hooks/useSheetFromQuery";
import { CameraSheet } from "./sheets/CameraSheet";
import { SensorSheet } from "./sheets/SensorSheet";
import { AssetSheet } from "./sheets/AssetSheet";
import type { SheetAction } from "./lib/sheetQuery";
import "./tokens/tokens.css";

type ListBootstrap = {
  authToken: string;
  isSuperuser: boolean;
  kind: "cam" | "sensor" | "asset";
  defaultSceneId?: string | null;
  scenes?: { id: string; name: string }[];
};

const CREATE_ACTIONS = new Set([
  "cam-create",
  "sensor-create",
  "asset-create",
]);

function isCreateAction(v: string | null): v is Exclude<SheetAction, null> {
  return Boolean(v && CREATE_ACTIONS.has(v));
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
      if (ss && isCreateAction(ss)) {
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

  if (!bootstrap.isSuperuser) {
    return null;
  }

  return (
    <>
      {bootstrap.kind === "cam" && (
        <CameraSheet
          open={sheet.action === "cam-create"}
          mode="create"
          sceneId={sceneId}
          scenes={scenes}
          sensorUid={null}
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
          sensorUid={null}
          authToken={bootstrap.authToken}
          onClose={close}
          onSaved={reload}
        />
      )}
      {bootstrap.kind === "asset" && (
        <AssetSheet
          open={sheet.action === "asset-create"}
          mode="create"
          assetUid={null}
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
