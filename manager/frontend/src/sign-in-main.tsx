// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadUiBootstrap } from "./lib/uiBootstrap";
import { SignInApp, type SignInBootstrap } from "./sign-in/SignInApp";
import "./tokens/tokens.css";

async function main(): Promise<void> {
  const bootstrap = await loadUiBootstrap<SignInBootstrap>(
    "ss-sign-in-bootstrap",
    "sign-in",
  );
  const host =
    document.getElementById("ss-sign-in-root") ||
    (() => {
      const el = document.createElement("div");
      el.id = "ss-sign-in-root";
      const mainEl =
        document.querySelector(".content") ||
        document.querySelector(".container-fluid") ||
        document.body;
      mainEl.appendChild(el);
      return el;
    })();
  if (!bootstrap) {
    return;
  }
  createRoot(host).render(
    <StrictMode>
      <SignInApp bootstrap={bootstrap} />
    </StrictMode>,
  );
}

void main();
