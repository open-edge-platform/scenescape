// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const PAGE_HOST_IDS: Record<string, string[]> = {
  chrome: ["ss-chrome-root"],
  scenes: ["ss-scenes-home-app", "ss-spa-root"],
  scene: ["ss-scene-detail-root", "ss-spa-root"],
  cameras: ["ss-admin-list-root", "ss-spa-root"],
  sensors: ["ss-admin-list-root", "ss-spa-root"],
  assets: ["ss-admin-list-root", "ss-spa-root"],
  models: ["ss-models-directory-root", "ss-spa-root"],
  "list-sheets": ["ss-list-sheets-root"],
  "sign-in": ["ss-sign-in-root"],
};

/**
 * Show a visible failure when ui-bootstrap cannot load (replaces blank islands).
 */
export function mountBootstrapError(
  page: string,
  detail: string,
  host?: HTMLElement | null,
): void {
  const candidates = PAGE_HOST_IDS[page] || [];
  let el = host || null;
  if (!el) {
    for (const id of candidates) {
      el = document.getElementById(id);
      if (el) {
        break;
      }
    }
  }
  if (!el) {
    el =
      (document.querySelector(".content") as HTMLElement | null) ||
      document.body;
  }
  if (!el || el.querySelector(".ss-bootstrap-error")) {
    return;
  }
  const banner = document.createElement("div");
  banner.className = "ss-bootstrap-error";
  banner.setAttribute("role", "alert");
  banner.style.cssText =
    "margin:1rem;padding:1rem 1.25rem;border:1px solid #b00020;" +
    "background:#fdecea;color:#611a15;border-radius:4px;font:14px/1.4 sans-serif;";
  const title = document.createElement("strong");
  title.textContent = "Unable to load this page";
  const body = document.createElement("p");
  body.style.margin = "0.5rem 0 0";
  body.textContent = detail;
  const hint = document.createElement("p");
  hint.style.margin = "0.5rem 0 0";
  hint.textContent = "Refresh the page, or sign in again if the session expired.";
  banner.append(title, body, hint);
  el.prepend(banner);
}
