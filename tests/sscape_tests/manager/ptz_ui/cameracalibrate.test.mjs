// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";

import {
  HOME,
  INTRINSICS,
  SCENE_ID,
  VERSION,
  isoAt,
  movedPose,
  poseContext,
  spy,
} from "./helpers.mjs";

const FORM = {
  "#id_intrinsics_fx": INTRINSICS[0],
  "#id_intrinsics_fy": INTRINSICS[1],
  "#id_intrinsics_cx": INTRINSICS[2],
  "#id_intrinsics_cy": INTRINSICS[3],
  "#id_distortion_k1": 0.007195,
  "#id_distortion_k2": 0,
  "#id_distortion_p1": 0,
  "#id_distortion_p2": 0,
  "#id_distortion_k3": 0,
};
const form = { submit: spy(), handlers: {} };
globalThis.$ = (selector) => {
  if (selector === "<canvas></canvas>") return [{ getContext: () => ({}) }];
  if (selector === "#calibration_form") {
    return Object.assign([form], {
      on: (event, handler) => (form.handlers[event] = handler),
    });
  }
  return { val: () => String(FORM[selector]) };
};
globalThis.Image = class {};
globalThis.alert = spy();

const { ConvergedCameraCalibration } =
  await import("/static/js/cameracalibrate.js");
const { Viewport } = await import("/static/js/viewport.js");
const { PTZ_AWAY_MESSAGE, PTZ_VIDEO_LATENCY_MS } =
  await import("/static/js/ptzpose.js");

function makeCalibration({ homeResponse } = {}) {
  const calibration = new ConvergedCameraCalibration();
  const shown = { state: "nothing" };
  calibration.camCanvas = {
    setPointMapper(mapper, visible) {
      shown.state = !visible ? "hidden" : mapper ? "moved" : "home";
      shown.mapper = mapper;
    },
    arePointsLocked: () => shown.state !== "home",
    updateImageSrc: spy(),
    getImageSize: () => [2688, 1512],
    getCalibrationPoints: () => ({}),
    calibrationUpdated: false,
  };
  calibration.viewport = {
    restClient: {
      getCamera: async () =>
        homeResponse ?? { statusCode: 200, content: { pose_matrix: HOME } },
    },
    setProjectionVisibility: spy(),
    setCameraPose: spy(),
    projectImage: spy(),
    getCalibrationPoints: () => ({}),
    calibrationUpdated: false,
  };
  calibration.projectionEnabled = true;
  calibration.isValidCalibration = () => false;
  return { calibration, shown };
}

function pose(calibration, options) {
  calibration.updatePTZPose(poseContext(options), SCENE_ID, VERSION, "cam");
}

function frame(calibration, seconds) {
  calibration.updateCalibrationViews(
    "data:image/jpeg;base64,",
    [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ],
    [0, 0, 0, 0, 0],
    isoAt(seconds),
  );
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function loadedAtHome() {
  const fixture = makeCalibration();
  pose(fixture.calibration, { timestamp: isoAt(0) });
  await flush();
  pose(fixture.calibration, { timestamp: isoAt(0.05) });
  return fixture;
}

test("points are shown immediately when no move was observed", () => {
  const { calibration, shown } = makeCalibration();
  calibration.ptzHomePoseMatrix = HOME;
  pose(calibration, { matrix: movedPose(0.2), timestamp: isoAt(0) });
  assert.equal(shown.state, "moved", "page opened while camera is parked away");
});

test("moved points appear with the first frame captured after the stop", async () => {
  const { calibration, shown } = await loadedAtHome();
  const latency = PTZ_VIDEO_LATENCY_MS / 1000;
  frame(calibration, 0.1);
  assert.equal(shown.state, "home");

  pose(calibration, { motionState: "slewing", timestamp: isoAt(2) });
  assert.equal(shown.state, "hidden");
  pose(calibration, { motionState: "settling", timestamp: isoAt(3) });
  assert.equal(shown.state, "hidden");

  const moved = movedPose(0.2);
  pose(calibration, { matrix: moved, timestamp: isoAt(4) });
  for (let i = 1; i <= 3; i++) {
    pose(calibration, { matrix: moved, timestamp: isoAt(4 + i * 0.05) });
  }
  assert.equal(shown.state, "hidden", "pose valid, video still lagging");
  frame(calibration, 3.5);
  assert.equal(shown.state, "hidden", "frame captured while moving");
  frame(calibration, 4 + latency - 0.01);
  assert.equal(shown.state, "hidden", "frame within the latency margin");
  frame(calibration, 4 + latency);
  assert.equal(shown.state, "moved");
  assert.equal(typeof shown.mapper, "function");

  pose(calibration, { matrix: moved, timestamp: isoAt(4 + latency + 0.1) });
  frame(calibration, 4 + latency + 0.2);
  assert.equal(shown.state, "moved", "stays after later poses and frames");
});

test("frames without a timestamp show pending points immediately", async () => {
  const { calibration, shown } = await loadedAtHome();
  pose(calibration, { motionState: "slewing", timestamp: isoAt(1) });
  pose(calibration, { matrix: movedPose(0.2), timestamp: isoAt(2) });
  calibration.updateCalibrationViews("data:", [[1]], [0], undefined);
  assert.equal(shown.state, "moved");
});

test("unknown position falls back to the stored home pose", async () => {
  const { calibration, shown } = await loadedAtHome();
  pose(calibration, { matrix: movedPose(0.2), timestamp: isoAt(1) });
  pose(calibration, { motionState: "unknown", timestamp: isoAt(2) });
  assert.equal(shown.state, "home");
  assert.equal(calibration.ptzPoseValid, true);
  assert.equal(calibration.isPTZAwayFromHome(), false);
  const homePose = calibration.viewport.setCameraPose.calls.at(-1)[0];
  assert.ok(homePose.elements.every(Number.isFinite));
});

test("a pose for another calibration version falls back to home", async () => {
  const { calibration, shown } = await loadedAtHome();
  pose(calibration, {
    matrix: movedPose(0.2),
    version: "cam-v2",
    timestamp: isoAt(1),
  });
  assert.equal(shown.state, "home");
  assert.equal(calibration.isPTZAwayFromHome(), false);
});

test("without a stored home pose the page behaves as for other cameras", async () => {
  const { calibration, shown } = makeCalibration({
    homeResponse: { statusCode: 404, content: {} },
  });
  pose(calibration, { timestamp: isoAt(0) });
  await flush();
  assert.equal(shown.state, "home");
  pose(calibration, { motionState: "unknown", timestamp: isoAt(1) });
  assert.equal(calibration.ptzPoseValid, null);
  assert.equal(shown.state, "home");
});

test("away from home covers moving and turned cameras", async () => {
  const { calibration } = await loadedAtHome();
  assert.equal(calibration.isPTZAwayFromHome(), false);
  pose(calibration, { motionState: "slewing", timestamp: isoAt(1) });
  assert.equal(calibration.isPTZAwayFromHome(), true);
  pose(calibration, { matrix: movedPose(0.2), timestamp: isoAt(2) });
  assert.equal(calibration.isPTZAwayFromHome(), true);
  pose(calibration, { matrix: HOME, timestamp: isoAt(3) });
  assert.equal(calibration.isPTZAwayFromHome(), false);
});

test("Save Camera is blocked away from home and allowed at home", async () => {
  const { calibration } = await loadedAtHome();
  calibration.setupSaveCameraButton();
  const submit = () => form.handlers.submit({ preventDefault() {} });

  pose(calibration, { matrix: movedPose(0.2), timestamp: isoAt(1) });
  globalThis.alert.calls.length = 0;
  form.submit.calls.length = 0;
  submit();
  assert.deepEqual(globalThis.alert.calls, [[PTZ_AWAY_MESSAGE]]);
  assert.equal(form.submit.calls.length, 0);

  pose(calibration, { matrix: HOME, timestamp: isoAt(2) });
  globalThis.alert.calls.length = 0;
  submit();
  assert.equal(globalThis.alert.calls.length, 0);
  assert.equal(form.submit.calls.length, 1);
});

test("frames are projected from the live pose and hidden while moving", async () => {
  const { calibration } = await loadedAtHome();
  const viewport = calibration.viewport;
  pose(calibration, { matrix: movedPose(0.2), timestamp: isoAt(1) });
  const live = calibration.ptzLiveMatrix;

  calibration.projectImage("data:", [[1]]);
  assert.equal(viewport.setCameraPose.calls.at(-1)[0], live);
  const [, , canProject] = viewport.projectImage.calls.at(-1);
  assert.equal(canProject(), true);

  pose(calibration, { motionState: "slewing", timestamp: isoAt(2) });
  assert.equal(canProject(), false, "late texture load is dropped");
  const projections = viewport.projectImage.calls.length;
  calibration.projectImage("data:", [[1]]);
  assert.equal(viewport.projectImage.calls.length, projections);
  assert.deepEqual(viewport.setProjectionVisibility.calls.at(-1), [false]);
});

test("viewport drops a texture that loads after projection became invalid", () => {
  const fake = {
    sceneMesh: {},
    projectedMaterial: null,
    projectionCamera: { updateProjectionMatrix: spy() },
    textureLoader: {
      load: (image, onLoad) => onLoad({ image: { width: 4, height: 3 } }),
    },
    drawObject: { createProjectionMaterial: spy(() => [{}, {}]) },
    add: spy(),
    setProjectionVisibility: spy(),
  };
  const intrinsics = [
    [10, 0, 2],
    [0, 10, 1.5],
    [0, 0, 1],
  ];
  Viewport.prototype.projectImage.call(fake, "data:", intrinsics, () => false);
  assert.equal(fake.drawObject.createProjectionMaterial.calls.length, 0);
  assert.equal(fake.setProjectionVisibility.calls.length, 0);

  Viewport.prototype.projectImage.call(fake, "data:", intrinsics);
  assert.equal(fake.drawObject.createProjectionMaterial.calls.length, 1);
  assert.deepEqual(fake.setProjectionVisibility.calls, [[true]]);
});
