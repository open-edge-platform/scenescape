// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

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

/** POST to a Django DeleteView URL, then navigate to the redirect Location or fallback. */
export async function postDjangoDelete(
  url: string,
  fallbackHref = "/",
): Promise<void> {
  const csrf = getCsrfToken();
  const body = new URLSearchParams();
  if (csrf) {
    body.set("csrfmiddlewaretoken", csrf);
  }
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrf,
    },
    body,
    credentials: "same-origin",
    redirect: "follow",
  });
  if (resp.redirected && resp.url) {
    window.location.href = resp.url;
    return;
  }
  if (resp.ok) {
    window.location.href = fallbackHref;
    return;
  }
  throw new Error(`Delete failed (HTTP ${resp.status})`);
}

export function inferDeleteLabel(href: string, linkText: string): string {
  const text = linkText.trim().toLowerCase();
  if (text.includes("camera") || href.includes("/cam/")) {
    return "camera";
  }
  if (text.includes("sensor") || href.includes("/singleton_sensor/")) {
    return "sensor";
  }
  if (text.includes("child") || href.includes("/child/")) {
    return "child scene link";
  }
  if (text.includes("scene") || /\/scene\/delete\//.test(href)) {
    return "scene";
  }
  return "item";
}
