// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Calibrate/create embeds: Cancel posts to the parent frame; forms keep embed=1.
 */
(function () {
  function bindEmbedBack() {
    document.querySelectorAll("[data-ss-embed-back]").forEach(function (btn) {
      if (btn.getAttribute("data-ss-bound") === "1") {
        return;
      }
      btn.setAttribute("data-ss-bound", "1");
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        var href = btn.getAttribute("data-ss-back-href") || "/";
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({ type: "ss-calibrate-cancel" }, "*");
          return;
        }
        window.location.assign(href);
      });
    });
  }

  document
    .querySelectorAll("form[method='post'], form[method='POST']")
    .forEach(function (form) {
      if (!form.querySelector('input[name="embed"]')) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "embed";
        input.value = "1";
        form.appendChild(input);
      }
    });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindEmbedBack);
  } else {
    bindEmbedBack();
  }
})();
