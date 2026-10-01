// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadUiBootstrap } from "./lib/uiBootstrap";
import { ensureSceneDetailDom } from "./lib/ensureSceneDetailDom";
import { sceneMapBitmapUrl } from "./lib/sceneMapBitmap";
import { SceneDetailApp } from "./scene/SceneDetailApp";
import type { SceneDetailBootstrap } from "./scene/types";
import "./tokens/tokens.css";
import "./scene-detail.css";

function sceneIdFromPath(): string | undefined {
  const m = window.location.pathname.match(
    /^\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?/i,
  );
  return m?.[1];
}

async function main(): Promise<void> {
  const bootstrap = await loadUiBootstrap<SceneDetailBootstrap>(
    "ss-scene-detail-bootstrap",
    "scene",
    sceneIdFromPath(),
  );
  const rootEl = document.getElementById("ss-scene-detail-root");
  if (!bootstrap || !rootEl) {
    return;
  }
  /* Prefer React map before sscape.js document.ready reads the flag. */
  window.ssUseReactMap = Boolean(sceneMapBitmapUrl(bootstrap.scene));
  window.ssReactOwnsMqtt = Boolean(window.ssUseReactMap);
  window.ssReactOwnsCameraStrip = Boolean(window.ssUseReactMap);
  ensureSceneDetailDom(bootstrap);
  document.documentElement.classList.add("ss-scene-workspace");
  document.body.classList.add("ss-scene-workspace");
  window.ssInitSceneMap?.(0);
  createRoot(rootEl).render(
    <StrictMode>
      <SceneDetailApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}

void main();
