// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Notify parent frame that an embedded create/edit/calibrate flow finished.
 * Optional data-ss-reload="true|false" on <body> controls whether the parent reloads.
 */
(function () {
  if (window.parent && window.parent !== window) {
    var reload = document.body
      ? document.body.getAttribute("data-ss-reload") !== "false"
      : true;
    window.parent.postMessage(
      { type: "ss-calibrate-done", reload: reload },
      window.location.origin,
    );
  } else {
    window.location.href = "/";
  }
})();
