// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Node test harness for SceneCamera.requestCalibrationFrame and the
 * native-resolution projection (invoked via pytest).
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { register } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
register("./stub_hooks.mjs", import.meta.url);

const JS_DIR = join(__dirname, "../../../manager/src/manager/static/js");
const { default: SceneCamera } = await import(
  pathToFileURL(join(JS_DIR, "thing/scenecamera.js")).href
);
const { FY, CMD_CAMERA, IMAGE_CALIBRATE } = await import(
  pathToFileURL(join(JS_DIR, "constants.js")).href
);

const APP = "scenescape";
const NAME = "camera1";
const FRAME_TOPIC = APP + IMAGE_CALIBRATE + NAME;
const CMD_TOPIC = APP + CMD_CAMERA + NAME;
const CALIB_FRAME_TIMEOUT = 15000;
const FY_VALUE = 1000;

class FakeMqttClient {
  constructor() {
    this.listeners = [];
    this.subscribed = [];
    this.unsubscribed = [];
    this.published = [];
  }
  on(event, fn) {
    assert.equal(event, "message");
    this.listeners.push(fn);
  }
  removeListener(event, fn) {
    this.listeners = this.listeners.filter((l) => l !== fn);
  }
  subscribe(topic, cb) {
    this.subscribed.push(topic);
    cb();
  }
  unsubscribe(topic) {
    this.unsubscribed.push(topic);
  }
  publish(topic, payload) {
    this.published.push([topic, payload]);
  }
  receive(topic, payload) {
    for (const listener of [...this.listeners]) listener(topic, payload);
  }
}

function makeCamera(overrides = {}) {
  const camera = Object.create(SceneCamera.prototype);
  Object.assign(camera, {
    name: NAME,
    appName: APP,
    mqttClient: new FakeMqttClient(),
    ...overrides,
  });
  return camera;
}

function makeProjectionCamera() {
  const intrinsicsUpdates = [];
  const camera = makeCamera({
    cameraMatrix: {
      data64F: Object.assign(new Array(9).fill(0), { [FY]: FY_VALUE }),
    },
    sceneCamera: { updateProjectionMatrix() {} },
    projectFrame: true,
    pauseVideo: false,
    cameraCapture: { project() {} },
    mesh: {},
    intrinsics: { fx: 1, fy: 1 },
    updateIntrinsics: (intrinsics) => intrinsicsUpdates.push(intrinsics),
  });
  camera.intrinsicsUpdates = intrinsicsUpdates;
  return camera;
}

function verticalFov(height) {
  return (2 * Math.atan(height / (2 * FY_VALUE)) * 180) / Math.PI;
}

function project(
  camera,
  data,
  texture = { image: { width: 960, height: 540 } },
) {
  globalThis.loadedTexture = texture;
  camera.projectCameraCapture("data:image/png;base64,AAAA", data, false);
}

test("requestCalibrationFrame rejects when MQTT is not connected", async () => {
  await assert.rejects(
    makeCamera({ mqttClient: null }).requestCalibrationFrame(),
    /MQTT is not connected/,
  );
  await assert.rejects(
    makeCamera({ appName: "" }).requestCalibrationFrame(),
    /MQTT is not connected/,
  );
});

test("requestCalibrationFrame requests the frame and resolves with the image", async () => {
  const camera = makeCamera();
  const client = camera.mqttClient;

  const pending = camera.requestCalibrationFrame();
  assert.deepEqual(client.subscribed, [FRAME_TOPIC]);
  assert.deepEqual(client.published, [[CMD_TOPIC, "getcalibrationimage"]]);

  client.receive(FRAME_TOPIC, JSON.stringify({ image: "native-frame" }));
  assert.equal(await pending, "native-frame");
  assert.deepEqual(client.unsubscribed, [FRAME_TOPIC]);
  assert.equal(client.listeners.length, 0);
});

test("requestCalibrationFrame ignores other topics and unusable messages", async () => {
  const camera = makeCamera();
  const client = camera.mqttClient;
  const pending = camera.requestCalibrationFrame();

  client.receive(
    APP + IMAGE_CALIBRATE + "other",
    JSON.stringify({ image: "wrong" }),
  );
  client.receive(FRAME_TOPIC, "{not json");
  client.receive(FRAME_TOPIC, JSON.stringify({ no_image: true }));
  assert.equal(client.listeners.length, 1);
  assert.deepEqual(client.unsubscribed, []);

  client.receive(FRAME_TOPIC, JSON.stringify({ image: "native-frame" }));
  assert.equal(await pending, "native-frame");
});

test("requestCalibrationFrame times out and cleans up", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const camera = makeCamera();
  const client = camera.mqttClient;
  const pending = camera.requestCalibrationFrame();

  t.mock.timers.tick(CALIB_FRAME_TIMEOUT - 1);
  assert.equal(client.listeners.length, 1);

  t.mock.timers.tick(1);
  await assert.rejects(pending, /timed out waiting for a calibration frame/);
  assert.deepEqual(client.unsubscribed, [FRAME_TOPIC]);
  assert.equal(client.listeners.length, 0);
});

test("projection uses the native resolution, not the preview size", () => {
  const camera = makeProjectionCamera();

  project(camera, { resolution: [3840, 2160] });

  assert.deepEqual(camera.resolution, { w: 3840, h: 2160 });
  assert.ok(Math.abs(camera.sceneCamera.fov - verticalFov(2160)) < 1e-9);
  assert.equal(camera.sceneCamera.aspect, 960 / 540);
});

test("projection falls back to the image size without a valid resolution", () => {
  for (const data of [
    {},
    null,
    { resolution: [3840] },
    { resolution: [0, 2160] },
    { resolution: [-3840, 2160] },
    { resolution: [NaN, 2160] },
    { resolution: ["3840", "2160"] },
    { resolution: "3840x2160" },
  ]) {
    const camera = makeProjectionCamera();

    project(camera, data);

    assert.deepEqual(
      camera.resolution,
      { w: 960, h: 540 },
      JSON.stringify(data),
    );
    assert.ok(Math.abs(camera.sceneCamera.fov - verticalFov(540)) < 1e-9);
  }
});

test("online projection passes the native resolution to the intrinsics update", () => {
  const camera = makeProjectionCamera();
  const calls = [];
  Object.assign(camera, {
    executeOnControl() {},
    showCameraOnline() {},
    updateCameraResolutionUsingInputFrame: (image, resolution) =>
      calls.push(resolution),
  });
  globalThis.loadedTexture = { image: { width: 960, height: 540 } };

  camera.projectCameraCapture("img", { resolution: [3840, 2160] });
  camera.projectCameraCapture("img", {});

  assert.deepEqual(calls, [{ w: 3840, h: 2160 }, null]);
});

test("input frame update centres the principal point on the native resolution", () => {
  let image;
  globalThis.Image = class {
    constructor() {
      image = this;
      this.width = 960;
      this.height = 540;
    }
  };
  const native = makeProjectionCamera();
  const preview = makeProjectionCamera();

  native.updateCameraResolutionUsingInputFrame("img", { w: 3840, h: 2160 });
  image.onload();
  preview.updateCameraResolutionUsingInputFrame("img");
  image.onload();

  assert.deepEqual(native.resolution, { w: 3840, h: 2160 });
  assert.equal(native.sceneCamera.aspect, 3840 / 2160);
  assert.deepEqual(native.intrinsicsUpdates[0], {
    fx: 1,
    fy: 1,
    cx: 1920,
    cy: 1080,
  });
  assert.deepEqual(preview.resolution, { w: 960, h: 540 });
  assert.deepEqual(preview.intrinsicsUpdates[0], {
    fx: 1,
    fy: 1,
    cx: 480,
    cy: 270,
  });
});
