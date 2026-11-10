// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "/static/assets/three.module.js";
import {
  PTZ_AWAY_MESSAGE,
  PTZ_CLOCK_SKEW_TOLERANCE_MS,
  PTZ_VIDEO_LATENCY_MS,
  PTZFrameGate,
  PTZPoseExpiry,
  ptzMatricesClose,
  sceneFromCameraToCameraMatrix,
} from "/static/js/ptzpose.js";
import {
  HOME,
  SCENE_ID,
  VERSION,
  isoAt,
  movedPose,
  poseContext,
  spy,
  UNKNOWN_POSITIONS,
} from "./helpers.mjs";

const { default: SceneCamera } =
  await import("/static/js/thing/scenecamera.js");
const { default: Scene } = await import("/static/js/thing/scene.js");
const { default: thingTransformControls } =
  await import("/static/js/thing/controls/thingtransformcontrols.js");

const POINTS = "3d-2d point correspondence";
const HOME_CAMERA = sceneFromCameraToCameraMatrix(HOME);

// A SceneCamera as addCamera() leaves it, without the browser-only constructor.
function makeCamera({ ptz = true, transformType = POINTS } = {}) {
  const camera = Object.create(SceneCamera.prototype);
  Object.assign(camera, thingTransformControls);
  const sceneCamera = new THREE.PerspectiveCamera(60, 16 / 9, 0.1, 10);
  HOME_CAMERA.decompose(
    sceneCamera.position,
    sceneCamera.quaternion,
    sceneCamera.scale,
  );
  sceneCamera.updateMatrix();
  return Object.assign(camera, {
    sceneCamera,
    cameraUID: "ptz-cam",
    name: "ptz-cam",
    previousName: "ptz-cam",
    sceneID: SCENE_ID,
    ptzSceneID: SCENE_ID,
    ptzCalibrationVersion: ptz ? VERSION : null,
    ptzPoseValid: null,
    ptzMoving: false,
    ptzFrameGate: new PTZFrameGate(),
    ptzPoseExpiry: new PTZPoseExpiry(),
    ptzLiveMatrix: null,
    ptzHomeMatrix: sceneCamera.matrix.clone(),
    transformType,
    isStoredInDB: true,
    mqttClient: null,
    isVARunning: false,
    mesh: { visible: true },
    resolution: { w: 1920, h: 1080 },
    hasAuthoritativeResolution: true,
    cameraMatrix: { data64F: [1000, 0, 960, 0, 1000, 540, 0, 0, 1] },
    toast: { showToast: spy() },
    updateExistingCamera: spy(async () => undefined),
    updateCameras: spy(),
    executeOnControl: spy(),
    enableAutoCalibration: spy(),
  });
}

function pose(camera, options) {
  camera.updatePTZPose(JSON.stringify(poseContext(options)));
}

function cameraMatrix(camera) {
  camera.sceneCamera.updateMatrix();
  return camera.sceneCamera.matrix;
}

test("a valid moved pose moves the camera and hides the old frame", () => {
  const camera = makeCamera();
  const moved = movedPose(0.2);
  pose(camera, { matrix: moved });
  assert.ok(
    ptzMatricesClose(
      cameraMatrix(camera),
      sceneFromCameraToCameraMatrix(moved),
    ),
  );
  assert.equal(camera.mesh.visible, false);
  assert.equal(camera.isPTZAwayFromHome(), true);
});

test("a moving camera is away from home and its frame is hidden", () => {
  const camera = makeCamera();
  pose(camera, { motionState: "slewing" });
  assert.equal(camera.ptzPoseValid, false);
  assert.equal(camera.mesh.visible, false);
  assert.equal(camera.isPTZAwayFromHome(), true);
  assert.ok(ptzMatricesClose(cameraMatrix(camera), HOME_CAMERA));
});

test("mismatched poses fall back to the home pose", () => {
  for (const fallback of [
    { matrix: movedPose(0.3), version: "cam-v2" },
    { matrix: movedPose(0.3), frameId: "scene:other" },
  ]) {
    const camera = makeCamera();
    pose(camera, { matrix: movedPose(0.2) });
    pose(camera, fallback);
    assert.ok(ptzMatricesClose(cameraMatrix(camera), HOME_CAMERA));
    assert.equal(camera.ptzPoseValid, true);
    assert.equal(camera.isPTZAwayFromHome(), false);
  }
});

test("unknown position shows the home pose but blocks save and auto calibration", async () => {
  for (const unknown of Object.values(UNKNOWN_POSITIONS)) {
    const camera = makeCamera();
    pose(camera, { matrix: movedPose(0.2) });
    pose(camera, unknown);
    assert.ok(ptzMatricesClose(cameraMatrix(camera), HOME_CAMERA));
    assert.equal(camera.ptzPoseValid, true);
    assert.equal(camera.isPTZAwayFromHome(), true, unknown.reasonDetail);

    await camera.saveSettings();
    globalThis.__ptzStubCalls = {};
    await camera.autoCalibrate();
    assert.equal(camera.updateExistingCamera.calls.length, 0);
    assert.equal(
      globalThis.__ptzStubCalls["js/calibration.js#startCameraCalibration"],
      undefined,
    );
    assert.equal(camera.toast.showToast.calls.length, 2, unknown.reasonDetail);

    pose(camera, { matrix: HOME });
    assert.equal(camera.isPTZAwayFromHome(), false, "valid pose at home");
  }
});

test("cameras without PTZ calibration are never away from home", () => {
  const camera = makeCamera({ ptz: false });
  camera.ptzMoving = true;
  assert.equal(camera.isPTZAwayFromHome(), false);
});

test("saving an unchanged point-calibrated camera keeps its points", async () => {
  const camera = makeCamera({ ptz: false });
  await camera.saveSettings();
  assert.deepEqual(camera.updateExistingCamera.calls, [
    [{ sensor_id: "ptz-cam", name: "ptz-cam", scene: SCENE_ID }],
  ]);
  assert.equal(camera.transformType, POINTS);
});

test("saving an edited pose stores it as an euler pose", async () => {
  const camera = makeCamera({ ptz: false });
  camera.sceneCamera.rotateZ(0.1);
  await camera.saveSettings();
  const [[payload]] = camera.updateExistingCamera.calls;
  assert.equal(payload.transform_type, "euler");
  assert.deepEqual(payload.scale, [1, 1, 1]);
  payload.translation.forEach((value, i) =>
    assert.ok(Math.abs(value - HOME[i][3]) < 1e-9),
  );
  assert.equal(camera.transformType, "euler");
});

test("saving an unchanged euler camera still sends its pose", async () => {
  const camera = makeCamera({ ptz: false, transformType: "euler" });
  await camera.saveSettings();
  const [[payload]] = camera.updateExistingCamera.calls;
  assert.equal(payload.transform_type, "euler");
  assert.equal(payload.rotation.length, 3);
});

test("saving is blocked while the PTZ camera is away from home or moving", async () => {
  for (const state of [
    { matrix: movedPose(0.2) },
    { motionState: "slewing" },
  ]) {
    const camera = makeCamera();
    pose(camera, state);
    await camera.saveSettings();
    assert.equal(camera.updateExistingCamera.calls.length, 0);
    assert.deepEqual(camera.toast.showToast.calls, [
      [PTZ_AWAY_MESSAGE, "warning"],
    ]);
  }
});

test("saving at home never stores the live pose and keeps the points", async () => {
  const camera = makeCamera();
  pose(camera, { matrix: movedPose(0.0002) });
  assert.equal(camera.isPTZAwayFromHome(), false);
  assert.equal(ptzMatricesClose(cameraMatrix(camera), HOME_CAMERA), false);
  await camera.saveSettings();
  assert.deepEqual(camera.updateExistingCamera.calls, [
    [{ sensor_id: "ptz-cam", name: "ptz-cam", scene: SCENE_ID }],
  ]);
});

test("auto calibration is blocked while the PTZ camera is away from home", async () => {
  const camera = makeCamera();
  pose(camera, { matrix: movedPose(0.2) });
  globalThis.__ptzStubCalls = {};
  await camera.autoCalibrate();
  assert.deepEqual(camera.toast.showToast.calls, [
    [PTZ_AWAY_MESSAGE, "warning"],
  ]);
  assert.equal(camera.enableAutoCalibration.calls.length, 0);
  assert.equal(
    globalThis.__ptzStubCalls["js/calibration.js#startCameraCalibration"],
    undefined,
  );
});

test("saving a scene that moves cameras is blocked while a PTZ is away", async () => {
  const makeScene = (away) => ({
    updateCamerasOnSave: true,
    sceneMesh: {},
    transformObject: null,
    name: "scene",
    pixelsPerMeter: 100,
    toast: { showToast: spy() },
    updateScene: spy(),
    executeOnControl: spy(),
    _applyMeshDeltaToCamerasAndSave: spy(async () => undefined),
    _getAllSceneCameraWrappers: () => [{ isPTZAwayFromHome: () => away }, {}],
  });

  const blocked = makeScene(true);
  await Scene.prototype.saveSettings.call(blocked);
  assert.deepEqual(blocked.toast.showToast.calls, [
    [PTZ_AWAY_MESSAGE, "warning"],
  ]);
  assert.equal(blocked.updateScene.calls.length, 0);
  assert.equal(blocked._applyMeshDeltaToCamerasAndSave.calls.length, 0);

  const allowed = makeScene(false);
  await Scene.prototype.saveSettings.call(allowed);
  assert.equal(allowed.toast.showToast.calls.length, 0);
  assert.equal(allowed._applyMeshDeltaToCamerasAndSave.calls.length, 1);
  assert.equal(allowed.updateScene.calls.length, 1);
});

// Texture loads complete when the test resolves them, like a slow image decode.
const pendingTextures = [];
THREE.TextureLoader.prototype.load = function (url, onLoad) {
  pendingTextures.push(onLoad);
};

function makeProjectingCamera() {
  const camera = makeCamera();
  return Object.assign(camera, {
    projectFrame: true,
    pauseVideo: false,
    cameraCapture: null,
    mesh: null,
    cameraMatrix: { data64F: [1000, 0, 960, 0, 1000, 540, 0, 0, 1] },
    sceneMesh: {},
    add: spy(),
    drawObj: {
      createProjectionMaterial: spy(() => [
        { opacity: 1, project: spy() },
        { visible: true },
      ]),
    },
  });
}

function captureFrame(camera, seconds) {
  pendingTextures.length = 0;
  camera.projectCameraCapture("data:", { timestamp: isoAt(seconds) }, false);
  return () =>
    pendingTextures.forEach((onLoad) =>
      onLoad({ image: { width: 1920, height: 1080 }, dispose() {} }),
    );
}

const projected = (camera) =>
  camera.drawObj.createProjectionMaterial.calls.length;

test("3D frames captured before the stop are not projected", () => {
  const camera = makeProjectingCamera();
  pose(camera, { motionState: "slewing", timestamp: isoAt(1) });
  pose(camera, { matrix: movedPose(0.2), timestamp: isoAt(2) });
  const cutoff = 2 + PTZ_VIDEO_LATENCY_MS / 1000;
  captureFrame(camera, cutoff - 0.01)();
  assert.equal(projected(camera), 0);
  captureFrame(camera, cutoff)();
  assert.equal(projected(camera), 1);
  assert.equal(camera.mesh.visible, true);
});

test("3D texture loads started for an earlier pose are dropped", () => {
  const camera = makeProjectingCamera();
  pose(camera, { matrix: HOME, timestamp: isoAt(0) });
  const finishLoad = captureFrame(camera, 0.1);
  pose(camera, { matrix: movedPose(0.2), timestamp: isoAt(1) });
  finishLoad();
  assert.equal(projected(camera), 0);
});

test("an expired retained pose shows the stored home pose in 3D", () => {
  const camera = makeCamera();
  pose(camera, { matrix: movedPose(0.2), timestamp: isoAt(-60) });
  assert.ok(ptzMatricesClose(cameraMatrix(camera), HOME_CAMERA));
  assert.equal(camera.isPTZAwayFromHome(), false);
});

test("the 3D live pose expires when Positioning stops publishing", (t) => {
  t.mock.timers.enable({
    apis: ["setTimeout", "Date"],
    now: Date.parse(isoAt(0)),
  });
  const camera = makeCamera();
  pose(camera, { matrix: movedPose(0.2), timestamp: isoAt(0) });
  assert.equal(camera.isPTZAwayFromHome(), true);
  t.mock.timers.tick(500 + PTZ_CLOCK_SKEW_TOLERANCE_MS - 1);
  assert.equal(camera.isPTZAwayFromHome(), true);
  t.mock.timers.tick(1);
  assert.ok(ptzMatricesClose(cameraMatrix(camera), HOME_CAMERA));
  assert.equal(camera.isPTZAwayFromHome(), false);
});
