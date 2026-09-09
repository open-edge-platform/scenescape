// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  ScenesHomeApp,
  type ScenesHomeBootstrap,
} from "./scenes/ScenesHomeApp";
import "./tokens/tokens.css";

function readBootstrap(): ScenesHomeBootstrap | null {
  const el = document.getElementById("ss-scenes-home-bootstrap");
  if (!el?.textContent) {
    return null;
  }
  try {
    return JSON.parse(el.textContent) as ScenesHomeBootstrap;
  } catch {
    console.error("Failed to parse scenes home bootstrap JSON");
    return null;
  }
}

const bootstrap = readBootstrap();
const host =
  document.getElementById("ss-scenes-home-app") ||
  (() => {
    const el = document.createElement("div");
    el.id = "ss-scenes-home-app";
    const main =
      document.querySelector("main") ||
      document.querySelector(".container") ||
      document.body;
    main.appendChild(el);
    return el;
  })();

if (bootstrap) {
  createRoot(host).render(
    <StrictMode>
      <ScenesHomeApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}
