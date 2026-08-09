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
const host = document.createElement("div");
host.id = "ss-scenes-home-root";
document.body.appendChild(host);

if (bootstrap) {
  createRoot(host).render(
    <StrictMode>
      <ScenesHomeApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}
