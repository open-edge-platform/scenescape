// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider } from "./components/ToastProvider";
import { loadUiBootstrap } from "./lib/uiBootstrap";
import { ModelsDirectoryApp } from "./models/ModelsDirectoryApp";
import "./tokens/tokens.css";

type Bootstrap = { isSuperuser?: boolean };

async function main(): Promise<void> {
  const bootstrap = await loadUiBootstrap<Bootstrap>(
    "ss-models-directory-bootstrap",
    "models",
  );
  const rootEl = document.getElementById("ss-models-directory-root");
  if (!bootstrap || !rootEl) {
    return;
  }
  createRoot(rootEl).render(
    <StrictMode>
      <ToastProvider>
        <ModelsDirectoryApp isSuperuser={Boolean(bootstrap.isSuperuser)} />
      </ToastProvider>
    </StrictMode>,
  );
}

void main();
