// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ModelsDirectoryApp } from "./models/ModelsDirectoryApp";
import "./tokens/tokens.css";

const rootEl = document.getElementById("ss-models-directory-root");
if (rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <ModelsDirectoryApp />
    </StrictMode>,
  );
}
