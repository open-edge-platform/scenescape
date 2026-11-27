// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";

let button;
globalThis.document = {
  addEventListener() {},
  getElementById(id) {
    if (id === "auto-autocalibration") return button;
    if (id === "calib-spinner") return { classList: { add() {}, remove() {} } };
    return null;
  },
};

// Loaded by path, not "/static/", so loader.mjs does not replace it with a stub.
const { manageCalibrationState } =
  await import("../../../../manager/src/manager/static/js/calibration.js");

function freshButton() {
  button = { disabled: false, title: "", dataset: {} };
  return button;
}

test("missing map keeps the button disabled with the server message", async () => {
  const btn = freshButton();
  await manageCalibrationState(
    { status: "error", message: "No map available for scene" },
    "scene-uid",
  );
  assert.equal(btn.disabled, true);
  assert.equal(btn.title, "No map available for scene");
  assert.equal(btn.dataset.registrationRetry, undefined);
});

test("insufficient tags keep the button disabled with the server message", async () => {
  const btn = freshButton();
  const message = "Cannot auto calibrate. Check scene map and AprilTags";
  await manageCalibrationState({ status: "error", message }, "scene-uid");
  assert.equal(btn.disabled, true);
  assert.equal(btn.title, message);
  assert.equal(btn.dataset.registrationRetry, undefined);
});

test("transient registration error stays retryable", async () => {
  const btn = freshButton();
  await manageCalibrationState(
    { status: "error", message: "Registration request timed out" },
    "scene-uid",
  );
  assert.equal(btn.disabled, false);
  assert.equal(
    btn.title,
    "Registration request timed out. Click to retry registration",
  );
  assert.equal(btn.dataset.registrationRetry, "1");
});
