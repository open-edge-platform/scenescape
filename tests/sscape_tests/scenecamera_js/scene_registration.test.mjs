// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { register } from "node:module";
import test from "node:test";
import { setImmediate } from "node:timers/promises";

register("./stub_hooks.mjs", import.meta.url);
globalThis.document = { addEventListener() {}, getElementById() {} };
const { registerSceneFor3DView } =
  await import("../../../manager/src/manager/static/js/calibration.js");
const { default: Toast } =
  await import("../../../manager/src/manager/static/js/toast.js");

const SCENE_ID = "scene-one";
const API = "/api/v1/autocalibration";
const REGISTRATION = `${API}/scenes/${SCENE_ID}/registration`;
const TOAST_ID = "scene-registration-toast";
const PROCESSING = "Processing the scene data to enable auto calibration";
const WAITING =
  "Another scene is being registered. Waiting to register this scene.";

function startRegistration(context, responses) {
  const requests = [];
  const polls = [];
  const notifications = [];
  const camera = {
    enabled: false,
    enableAutoCalibration(value) {
      this.enabled = value;
    },
  };
  const toast = {
    showToast: (...args) => notifications.push(["show", ...args]),
    updateToast: (...args) => notifications.push(["update", ...args]),
  };
  context.mock.method(document, "getElementById", (id) => ({
    remove: () => notifications.push(["remove", id]),
  }));
  context.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push([url, options?.method ?? "GET"]);
    const status = url === `${API}/status` ? "running" : responses.shift();
    return { ok: true, json: async () => ({ status }) };
  });
  context.mock.method(globalThis, "setTimeout", (callback) => {
    polls.push(callback);
  });

  const done = registerSceneFor3DView(SCENE_ID, { camera }, toast);
  return {
    camera,
    done,
    notifications,
    requests,
    async poll() {
      assert.equal(polls.length, 1, "one follow-up status check is queued");
      polls.shift()();
      await setImmediate();
    },
  };
}

test("the 3D view shows registration progress and enables the same camera when ready", async (context) => {
  const view = startRegistration(context, [
    "registering",
    "registering",
    "registering",
    "success",
  ]);
  await setImmediate();
  assert.equal(view.camera.enabled, false);
  assert.deepEqual(view.notifications, [
    ["show", PROCESSING, "default", TOAST_ID, null],
  ]);

  await view.poll();
  assert.equal(view.camera.enabled, false);
  assert.equal(view.notifications.length, 1);

  await view.poll();
  await view.done;
  assert.equal(view.camera.enabled, true);
  assert.deepEqual(view.notifications.slice(1), [
    ["remove", TOAST_ID],
    ["show", "Dataset registered", "success", "None", 10000],
  ]);
  assert.deepEqual(view.requests, [
    [`${API}/status`, "GET"],
    [REGISTRATION, "POST"],
    [REGISTRATION, "GET"],
    [REGISTRATION, "POST"],
    [REGISTRATION, "GET"],
  ]);
});

test("the 3D view waits for another scene, then registers this scene", async (context) => {
  const view = startRegistration(context, [
    "busy",
    "busy",
    "registering",
    "registering",
    "success",
  ]);
  await setImmediate();
  assert.deepEqual(view.notifications, [
    ["show", WAITING, "default", TOAST_ID, null],
  ]);

  await view.poll();
  assert.equal(
    view.requests.filter(([, method]) => method === "POST").length,
    1,
  );
  await view.poll();
  assert.equal(view.camera.enabled, false);
  assert.deepEqual(view.notifications.slice(1), [
    ["update", TOAST_ID, PROCESSING],
  ]);

  await view.poll();
  await view.done;
  assert.equal(view.camera.enabled, true);
  assert.deepEqual(
    view.requests.filter(([, method]) => method === "POST"),
    [
      [REGISTRATION, "POST"],
      [REGISTRATION, "POST"],
    ],
  );
});

test("a failed registration result leaves Auto Calibrate disabled", async (context) => {
  context.mock.method(console, "warn", () => {});
  const view = startRegistration(context, ["registering", "error"]);
  await setImmediate();
  await view.poll();
  await view.done;
  assert.equal(view.camera.enabled, false);
  assert.deepEqual(view.notifications.slice(1), [
    ["remove", TOAST_ID],
    [
      "show",
      "Scene registration could not be completed",
      "danger",
      "None",
      10000,
    ],
  ]);
});

test("persistent toasts disable autohide without passing a null Bootstrap delay", (context) => {
  const element = {
    addEventListener() {},
    appendChild() {},
    setAttribute() {},
  };
  const previousDocument = globalThis.document;
  globalThis.document = {
    getElementById: () => element,
    createElement: () => ({ ...element }),
    querySelector: () => element,
  };
  const calls = [];
  globalThis.$ = () => ({ toast: (option) => calls.push(option) });
  context.after(() => {
    globalThis.document = previousDocument;
    delete globalThis.$;
  });

  Toast().showToast(PROCESSING, "default", TOAST_ID, null);
  assert.deepEqual(calls, [{ autohide: false }, "show"]);
});
