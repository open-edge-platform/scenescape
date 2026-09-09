// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

(function (global) {
  "use strict";

  var STORAGE_KEY = "ss-theme";
  var THEMES = { light: true, dark: true };

  function normalize(theme) {
    return THEMES[theme] ? theme : "light";
  }

  function getTheme() {
    try {
      return normalize(global.localStorage.getItem(STORAGE_KEY));
    } catch (e) {
      return "light";
    }
  }

  function applyTheme(theme) {
    var next = normalize(theme);
    document.documentElement.setAttribute("data-theme", next);
    var root = document.getElementById("ss-theme-toggle");
    if (!root) {
      return;
    }
    root.querySelectorAll("[data-ss-theme]").forEach(function (btn) {
      var value = btn.getAttribute("data-ss-theme");
      btn.setAttribute("aria-pressed", value === next ? "true" : "false");
    });
  }

  function setTheme(theme) {
    var next = normalize(theme);
    try {
      global.localStorage.setItem(STORAGE_KEY, next);
    } catch (e) {
      /* private mode / quota */
    }
    applyTheme(next);
  }

  function initThemeToggle() {
    applyTheme(getTheme());
    var root = document.getElementById("ss-theme-toggle");
    if (!root || root.getAttribute("data-ss-bound") === "1") {
      return;
    }
    root.setAttribute("data-ss-bound", "1");
    root.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-ss-theme]");
      if (!btn || !root.contains(btn)) {
        return;
      }
      setTheme(btn.getAttribute("data-ss-theme"));
    });
  }

  global.ssTheme = {
    getTheme: getTheme,
    setTheme: setTheme,
    applyTheme: applyTheme,
    initThemeToggle: initThemeToggle,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initThemeToggle);
  } else {
    initThemeToggle();
  }
})(window);
