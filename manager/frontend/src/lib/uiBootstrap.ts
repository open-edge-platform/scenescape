// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { readBootstrapJson } from "./bootstrap";
import { persistAuthToken, readAuthToken } from "./authToken";
import { mountBootstrapError } from "./bootstrapError";

export type UiBootstrapPage =
  | "chrome"
  | "scenes"
  | "scene"
  | "cameras"
  | "sensors"
  | "assets"
  | "models"
  | "list-sheets"
  | "sign-in";

function rememberBootstrapToken(payload: unknown): void {
  if (
    payload &&
    typeof payload === "object" &&
    typeof (payload as { authToken?: unknown }).authToken === "string"
  ) {
    persistAuthToken((payload as { authToken: string }).authToken);
  }
}

/**
 * Prefer embedded `json_script`, else GET /api/v1/ui-bootstrap/ (session or Token).
 * Enables static shells without Django page templates.
 * On failure (non-401), mounts a visible error banner and returns null.
 */
export async function loadUiBootstrap<T>(
  elementId: string,
  page: UiBootstrapPage,
  entityId?: string,
): Promise<T | null> {
  const embedded = readBootstrapJson<T>(elementId);
  if (embedded) {
    rememberBootstrapToken(embedded);
    return embedded;
  }
  const params = new URLSearchParams({ page });
  if (entityId) {
    params.set("id", entityId);
  }
  const headers: HeadersInit = {};
  const token = readAuthToken();
  if (token) {
    headers.Authorization = `Token ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1/ui-bootstrap/?${params.toString()}`, {
      credentials: "same-origin",
      headers,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Network error";
    console.error(`ui-bootstrap failed: ${page}`, err);
    mountBootstrapError(page, `Could not reach ui-bootstrap (${msg}).`);
    return null;
  }
  if (res.status === 401) {
    const next = encodeURIComponent(
      `${window.location.pathname}${window.location.search}`,
    );
    window.location.href = `/sign_in/?next=${next}`;
    return null;
  }
  if (!res.ok) {
    console.error(`ui-bootstrap failed: ${res.status} ${page}`);
    mountBootstrapError(
      page,
      `ui-bootstrap returned HTTP ${res.status} for page="${page}".`,
    );
    return null;
  }
  const payload = (await res.json()) as T;
  rememberBootstrapToken(payload);
  return payload;
}
