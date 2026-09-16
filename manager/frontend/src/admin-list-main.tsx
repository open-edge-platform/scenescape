// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AdminListApp, type AdminListBootstrap } from "./admin/AdminListApp";
import "./tokens/tokens.css";

function readBootstrap(): AdminListBootstrap | null {
  const el = document.getElementById("ss-admin-list-bootstrap");
  if (!el?.textContent) {
    return null;
  }
  try {
    return JSON.parse(el.textContent) as AdminListBootstrap;
  } catch {
    console.error("Failed to parse admin list bootstrap JSON");
    return null;
  }
}

const bootstrap = readBootstrap();
const rootEl = document.getElementById("ss-admin-list-root");

if (bootstrap && rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <AdminListApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}
