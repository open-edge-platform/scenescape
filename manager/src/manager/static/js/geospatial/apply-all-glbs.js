// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Classic script for the scene home page. The switch state lives on the server (Scene.glb_apply_all):
// a change is sent with PUT, the checkbox reverts and the server message is shown on failure,
// and the page reloads on success so the map, scale and map origin match the new state.

/**
 * Send the switch state to the server.
 *
 * @param {{checked: boolean, disabled: boolean, dataset: {url: string}}} toggle the switch input
 */
async function setApplyAllGlbs(toggle) {
  const apply = toggle.checked;
  toggle.disabled = true;
  try {
    await requestJson(toggle.dataset.url, {
      method: "PUT",
      body: { apply },
      requireCsrf: true,
    });
    window.location.reload();
  } catch (error) {
    toggle.checked = !apply;
    window.alert(`Apply all GLBs failed: ${error.message}`);
  } finally {
    toggle.disabled = false;
  }
}

/**
 * Bind the Apply all GLBs switch to the server call.
 *
 * @param {{addEventListener: Function}} toggle the switch input
 */
function bindApplyAllGlbs(toggle) {
  toggle.addEventListener("change", () => setApplyAllGlbs(toggle));
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("apply-all-glbs");
    if (toggle) bindApplyAllGlbs(toggle);
  });
}
