// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Static-shell entry: chrome + page islands from ui-bootstrap API.
 * Mounted by /static/ui/shell.html (no Django page template).
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadUiBootstrap } from "./lib/uiBootstrap";
import { ensureSceneDetailDom } from "./lib/ensureSceneDetailDom";
import { sceneMapBitmapUrl } from "./lib/sceneMapBitmap";
import { AppChrome } from "./chrome/AppChrome";
import type { ChromeBootstrap } from "./chrome/types";
import {
  ScenesHomeApp,
  type ScenesHomeBootstrap,
} from "./scenes/ScenesHomeApp";
import { SceneDetailApp } from "./scene/SceneDetailApp";
import type { SceneDetailBootstrap } from "./scene/types";
import { AdminListApp, type AdminListBootstrap } from "./admin/AdminListApp";
import { ToastProvider } from "./components/ToastProvider";
import { ModelsDirectoryApp } from "./models/ModelsDirectoryApp";
import "./tokens/tokens.css";
import "./scene-detail.css";

function sceneIdFromPath(): string | null {
  const m = window.location.pathname.match(
    /^\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?/i,
  );
  return m?.[1] ?? null;
}

function listKindFromPath(): "cameras" | "sensors" | "assets" | "models" | null {
  const path = window.location.pathname;
  if (path.includes("/cam/list") || path.startsWith("/cameras")) {
    return "cameras";
  }
  if (
    path.includes("/singleton_sensor/list") ||
    path.startsWith("/sensors")
  ) {
    return "sensors";
  }
  if (path.includes("/asset/list") || path.startsWith("/assets")) {
    return "assets";
  }
  if (path.includes("/model/list") || path.startsWith("/models")) {
    return "models";
  }
  return null;
}

async function mountChrome(): Promise<void> {
  const bootstrap = await loadUiBootstrap<ChromeBootstrap>(
    "ss-chrome-bootstrap",
    "chrome",
  );
  const host = document.getElementById("ss-chrome-root");
  if (!bootstrap || !host) {
    return;
  }
  createRoot(host).render(
    <StrictMode>
      <AppChrome bootstrap={bootstrap} />
    </StrictMode>,
  );
}

async function mountAdminList(
  spaRoot: HTMLElement,
  page: "cameras" | "sensors" | "assets",
): Promise<void> {
  const bootstrap = await loadUiBootstrap<AdminListBootstrap>(
    "ss-admin-list-bootstrap",
    page,
  );
  if (!bootstrap) {
    return;
  }
  const listRoot = document.createElement("div");
  listRoot.id = "ss-admin-list-root";
  spaRoot.appendChild(listRoot);
  createRoot(listRoot).render(
    <StrictMode>
      <AdminListApp bootstrap={bootstrap} />
    </StrictMode>,
  );
  // Sheets island is a separate entry; dynamic import runs its mount.
  await import("./list-sheets-main");
}

async function mountModels(spaRoot: HTMLElement): Promise<void> {
  const bootstrap = await loadUiBootstrap<{ isSuperuser?: boolean }>(
    "ss-models-directory-bootstrap",
    "models",
  );
  if (!bootstrap) {
    return;
  }
  const root = document.createElement("div");
  root.id = "ss-models-directory-root";
  spaRoot.appendChild(root);
  createRoot(root).render(
    <StrictMode>
      <ToastProvider>
        <ModelsDirectoryApp isSuperuser={Boolean(bootstrap.isSuperuser)} />
      </ToastProvider>
    </StrictMode>,
  );
}

async function mountPage(): Promise<void> {
  const spaRoot = document.getElementById("ss-spa-root");
  if (!spaRoot) {
    return;
  }
  const sceneId = sceneIdFromPath();
  if (sceneId) {
    const bootstrap = await loadUiBootstrap<SceneDetailBootstrap>(
      "ss-scene-detail-bootstrap",
      "scene",
      sceneId,
    );
    if (!bootstrap) {
      return;
    }
    const detailRoot = document.createElement("div");
    detailRoot.id = "ss-scene-detail-root";
    detailRoot.className = "ss-scene-detail-root";
    spaRoot.appendChild(detailRoot);
    window.ssUseReactMap = Boolean(sceneMapBitmapUrl(bootstrap.scene));
    window.ssReactOwnsMqtt = Boolean(window.ssUseReactMap);
    window.ssReactOwnsCameraStrip = Boolean(window.ssUseReactMap);
    ensureSceneDetailDom(bootstrap);
    window.ssRefreshSceneId?.();
    document.documentElement.classList.add("ss-scene-workspace");
    document.body.classList.add("ss-scene-workspace");
    window.ssInitSceneMap?.(0);
    createRoot(detailRoot).render(
      <StrictMode>
        <SceneDetailApp bootstrap={bootstrap} />
      </StrictMode>,
    );
    return;
  }

  const listKind = listKindFromPath();
  if (listKind === "models") {
    await mountModels(spaRoot);
    return;
  }
  if (listKind) {
    await mountAdminList(spaRoot, listKind);
    return;
  }

  const bootstrap = await loadUiBootstrap<ScenesHomeBootstrap>(
    "ss-scenes-home-bootstrap",
    "scenes",
  );
  if (!bootstrap) {
    return;
  }
  const homeRoot = document.createElement("div");
  homeRoot.id = "ss-scenes-home-app";
  spaRoot.appendChild(homeRoot);
  createRoot(homeRoot).render(
    <StrictMode>
      <ScenesHomeApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}

async function main(): Promise<void> {
  await mountChrome();
  await mountPage();
}

void main();
