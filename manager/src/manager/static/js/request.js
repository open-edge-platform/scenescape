// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Classic script: its functions are globals for other classic scripts and ES modules alike.

/** The Django CSRF token of the page's form, or null when the page has none. */
function getCsrfToken() {
  return document.querySelector("[name=csrfmiddlewaretoken]")?.value || null;
}

/**
 * Send a request with the CSRF header and return the parsed JSON body.
 *
 * Plain object bodies are sent as JSON; FormData is sent as is. Resolves to {} for a 204 or a
 * body that is not JSON (e.g. a proxy error). Rejects with an Error carrying `status` and the
 * parsed `data` when the response is not ok.
 *
 * @param {string} url
 * @param {object} [options]
 * @param {string} [options.method="GET"]
 * @param {object|FormData} [options.body]
 * @param {object} [options.headers] extra request headers
 * @param {string|null} [options.csrfToken] defaults to getCsrfToken()
 * @param {boolean} [options.requireCsrf=false] reject before sending when there is no token
 * @param {(status: number) => string} [options.errorMessage] message when the body has no `error`
 */
async function requestJson(
  url,
  {
    method = "GET",
    body,
    headers = {},
    csrfToken = getCsrfToken(),
    requireCsrf = false,
    errorMessage = (status) => `Request failed (${status})`,
  } = {},
) {
  if (requireCsrf && !csrfToken) throw new Error("CSRF token not found");
  const requestHeaders = {};
  if (csrfToken) requestHeaders["X-CSRFToken"] = csrfToken;
  if (body && !(body instanceof FormData)) {
    requestHeaders["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(url, {
    method,
    headers: { ...requestHeaders, ...headers },
    body,
  });
  if (response.status === 204) return {};
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || errorMessage(response.status));
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}
