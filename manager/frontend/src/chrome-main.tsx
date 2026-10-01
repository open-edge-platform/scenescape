// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadUiBootstrap } from "./lib/uiBootstrap";
import { AppChrome } from "./chrome/AppChrome";
import type { ChromeBootstrap } from "./chrome/types";
import "./tokens/tokens.css";

async function main(): Promise<void> {
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

void main();
