// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider } from "./components/ToastProvider";
import { LegacyConfirmHost } from "./components/LegacyConfirmHost";
import { useDeleteLinkInterceptor } from "./hooks/useDeleteLinkInterceptor";
import "./tokens/tokens.css";
import "./components/ConfirmDialog.css";
import "./components/Button.css";

function DestructiveActionsApp() {
  const { dialog } = useDeleteLinkInterceptor({
    fallbackHref: "/",
  });
  return dialog;
}

const host = document.createElement("div");
host.id = "ss-destructive-actions-root";
document.body.appendChild(host);

createRoot(host).render(
  <StrictMode>
    <ToastProvider>
      <LegacyConfirmHost>
        <DestructiveActionsApp />
      </LegacyConfirmHost>
    </ToastProvider>
  </StrictMode>,
);
