// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { readBootstrapJson } from "./bootstrap";

const BOOTSTRAP_TOKEN_IDS = [
  "ss-auth-bootstrap",
  "ss-scene-detail-bootstrap",
  "ss-scenes-home-bootstrap",
  "ss-list-sheets-bootstrap",
  "ss-models-directory-bootstrap",
  "ss-admin-list-bootstrap",
] as const;

/** In-memory token from ui-bootstrap API (static shells have no json_script). */
let persistedAuthToken = "";

/**
 * Remember a Token from fetched ui-bootstrap payloads so later REST calls
 * (e.g. model-directory) do not depend on Django `ss-auth-bootstrap`.
 */
export function persistAuthToken(token: string): void {
  if (token) {
    persistedAuthToken = token;
  }
}

/**
 * DRF Token for portable `/api/v1` calls. Prefers an in-memory token from
 * ui-bootstrap, then page-wide `ss-auth-bootstrap`, then island bootstraps,
 * then legacy `#auth-token`.
 */
export function readAuthToken(): string {
  if (persistedAuthToken) {
    return persistedAuthToken;
  }
  for (const id of BOOTSTRAP_TOKEN_IDS) {
    if (id === "ss-auth-bootstrap") {
      const el = document.getElementById(id);
      if (!el?.textContent) {
        continue;
      }
      try {
        const parsed = JSON.parse(el.textContent);
        if (typeof parsed === "string" && parsed) {
          return parsed;
        }
        if (
          parsed &&
          typeof parsed === "object" &&
          typeof (parsed as { authToken?: string }).authToken === "string"
        ) {
          return (parsed as { authToken: string }).authToken;
        }
      } catch {
        /* ignore */
      }
      continue;
    }
    const boot = readBootstrapJson<{ authToken?: string }>(id);
    if (boot?.authToken) {
      return boot.authToken;
    }
  }
  const legacy = document.getElementById(
    "auth-token",
  ) as HTMLInputElement | null;
  return legacy?.value?.trim() || "";
}
