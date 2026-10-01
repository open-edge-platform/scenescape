// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadUiBootstrap } from "./lib/uiBootstrap";
import {
  ScenesHomeApp,
  type ScenesHomeBootstrap,
} from "./scenes/ScenesHomeApp";
import "./tokens/tokens.css";

async function main(): Promise<void> {
  const bootstrap = await loadUiBootstrap<ScenesHomeBootstrap>(
    "ss-scenes-home-bootstrap",
    "scenes",
  );
  const host =
    document.getElementById("ss-scenes-home-app") ||
    (() => {
      const el = document.createElement("div");
      el.id = "ss-scenes-home-app";
      const mainEl =
        document.querySelector("main") ||
        document.querySelector(".content") ||
        document.querySelector(".container") ||
        document.body;
      mainEl.appendChild(el);
      return el;
    })();

  if (!bootstrap) {
    return;
  }
  createRoot(host).render(
    <StrictMode>
      <ScenesHomeApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}

void main();
