// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Node test harness for SceneCamera.requestCalibrationFrame (invoked via pytest).
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
const { CMD_CAMERA, IMAGE_CALIBRATE } = await import(
  pathToFileURL(join(JS_DIR, "constants.js")).href
);

const APP = "scenescape";
const NAME = "camera1";
const FRAME_TOPIC = APP + IMAGE_CALIBRATE + NAME;
const CMD_TOPIC = APP + CMD_CAMERA + NAME;
const CALIB_FRAME_TIMEOUT = 15000;

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
  try {
    t.mock.timers.enable({ apis: ["setTimeout"] });
  } catch {
    t.mock.timers.enable(["setTimeout"]); // Node 18 takes an array
  }
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
