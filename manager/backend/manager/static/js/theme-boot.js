// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Apply stored theme before first paint (FOUC prevention).
 * Kept as an external file so CSP script-src 'self' allows it.
 */
(function () {
  try {
    var t = localStorage.getItem("ss-theme");
    document.documentElement.setAttribute(
      "data-theme",
      t === "dark" || t === "light" ? t : "light",
    );
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "light");
  }
})();
