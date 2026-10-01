// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Portable session helpers for Manager islands.
 *
 * Token REST (`lib/rest.ts`) is the long-term auth path. Session + CSRF is
 * transitional for DeleteViews, mesh generation, and model-directory until
 * those move behind Token APIs. Feature code should call these helpers rather
 * than reading `csrfmiddlewaretoken` or `csrftoken` directly.
 *
 * See docs/design/manager-ui-backend-contract.md §5.2.
 */

export function getCsrfToken(): string {
  const input = document.querySelector(
    'input[name="csrfmiddlewaretoken"]',
  ) as HTMLInputElement | null;
  if (input?.value) {
    return input.value;
  }
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

/** Headers for Token-authenticated `/api/v1` calls. */
export function tokenAuthHeaders(token: string): HeadersInit {
  return token ? { Authorization: `Token ${token}` } : {};
}

/** CSRF header for session-authenticated mutating requests. */
export function csrfHeaders(extra?: HeadersInit): HeadersInit {
  const csrf = getCsrfToken();
  return {
    ...(csrf ? { "X-CSRFToken": csrf } : {}),
    ...extra,
  };
}

function methodNeedsCsrf(method: string): boolean {
  const m = method.toUpperCase();
  return m !== "GET" && m !== "HEAD" && m !== "OPTIONS" && m !== "TRACE";
}

/**
 * `fetch` with same-origin credentials and CSRF on mutating methods.
 * Prefer `lib/rest.ts` for Token CRUD.
 */
export async function sessionFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const method = init.method || "GET";
  const headers = new Headers(init.headers || {});
  if (methodNeedsCsrf(method) && !headers.has("X-CSRFToken")) {
    const csrf = getCsrfToken();
    if (csrf) {
      headers.set("X-CSRFToken", csrf);
    }
  }
  return fetch(input, {
    ...init,
    credentials: init.credentials ?? "same-origin",
    headers,
  });
}
