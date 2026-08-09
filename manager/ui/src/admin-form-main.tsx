// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AdminFormApp, type AdminFormBootstrap } from "./admin/AdminFormApp";
import "./tokens/tokens.css";

function readBootstrap(): AdminFormBootstrap | null {
  const el = document.getElementById("ss-admin-form-bootstrap");
  if (!el?.textContent) {
    return null;
  }
  try {
    return JSON.parse(el.textContent) as AdminFormBootstrap;
  } catch {
    console.error("Failed to parse admin form bootstrap JSON");
    return null;
  }
}

const bootstrap = readBootstrap();
const rootEl = document.getElementById("ss-admin-form-root");

if (bootstrap && rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <AdminFormApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}
