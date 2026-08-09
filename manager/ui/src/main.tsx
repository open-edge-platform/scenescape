// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SceneDetailApp } from "./scene/SceneDetailApp";
import type { SceneDetailBootstrap } from "./scene/types";
import "./tokens/tokens.css";
import "./scene-detail.css";

function readBootstrap(): SceneDetailBootstrap | null {
  const el = document.getElementById("ss-scene-detail-bootstrap");
  if (!el?.textContent) {
    return null;
  }
  try {
    return JSON.parse(el.textContent) as SceneDetailBootstrap;
  } catch {
    console.error("Failed to parse scene detail bootstrap JSON");
    return null;
  }
}

const bootstrap = readBootstrap();
const rootEl = document.getElementById("ss-scene-detail-root");

if (bootstrap && rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <SceneDetailApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}
