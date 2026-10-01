// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AdminListApp, type AdminListBootstrap } from "./admin/AdminListApp";
import { loadUiBootstrap, type UiBootstrapPage } from "./lib/uiBootstrap";
import "./tokens/tokens.css";

function listPageFromPath(): UiBootstrapPage | null {
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
  return null;
}

async function main(): Promise<void> {
  const page = listPageFromPath();
  if (!page) {
    console.error("admin-list: unrecognized list path");
    return;
  }
  const bootstrap = await loadUiBootstrap<AdminListBootstrap>(
    "ss-admin-list-bootstrap",
    page,
  );
  const rootEl = document.getElementById("ss-admin-list-root");
  if (!bootstrap || !rootEl) {
    return;
  }
  createRoot(rootEl).render(
    <StrictMode>
      <AdminListApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}

void main();
