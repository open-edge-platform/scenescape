// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider } from "./components/ToastProvider";
import { ModelsDirectoryApp } from "./models/ModelsDirectoryApp";
import "./tokens/tokens.css";

type Bootstrap = { isSuperuser?: boolean };

function readBootstrap(): Bootstrap {
  const el = document.getElementById("ss-models-directory-bootstrap");
  if (!el?.textContent) {
    return {};
  }
  try {
    return JSON.parse(el.textContent) as Bootstrap;
  } catch {
    console.error("Failed to parse models directory bootstrap JSON");
    return {};
  }
}

const bootstrap = readBootstrap();
const rootEl = document.getElementById("ss-models-directory-root");
if (rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <ToastProvider>
        <ModelsDirectoryApp isSuperuser={Boolean(bootstrap.isSuperuser)} />
      </ToastProvider>
    </StrictMode>,
  );
}
