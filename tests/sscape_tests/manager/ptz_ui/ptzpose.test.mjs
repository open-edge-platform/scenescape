// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "/static/assets/three.module.js";
import {
  PTZ_HOME_ANGLE_TOLERANCE_RAD,
  PTZ_VIDEO_LATENCY_MS,
  PTZFrameGate,
  PTZPoseExpiry,
  createPTZPointMapper,
  isPTZAwayFromHomePose,
  isPTZMoving,
  isPTZPoseExpired,
  ptzMatricesClose,
  ptzPoseToCameraMatrix,
  sceneFromCameraToCameraMatrix,
} from "/static/js/ptzpose.js";
import {
  HOME,
  IMAGE_SIZE,
  INTRINSICS,
  SCENE_ID,
  VERSION,
  isoAt,
  movedPose,
  poseContext,
  project,
  rotationXYZ,
  spy,
  withRotation,
} from "./helpers.mjs";

const LENSES = {
  none: [0, 0, 0, 0, 0],
  lab: [0.007195, 0, 0, 0, 0],
  barrel: [-0.32, 0.11, 0.0012, -0.0008, -0.015],
  pincushion: [0.18, 0.05, -0.001, 0.0015, 0.01],
};

// The stored-pose path of the 3D UI: euler pose, then y-down to y-up conversion.
function storedPoseCameraMatrix(translation, rotationDeg) {
  const camera = new THREE.Object3D();
  camera.position.fromArray(translation);
  camera.rotation.fromArray(rotationDeg.map(THREE.MathUtils.degToRad));
  camera.rotateY(Math.PI);
  camera.rotateZ(Math.PI);
  camera.updateMatrix();
  return camera.matrix;
}

test("valid stationary pose converts like the stored euler pose", () => {
  for (const [translation, rotationDeg] of [
    [
      [1.5, -2, 3.1],
      [-130, 12, 45],
    ],
    [
      [0, 0, 2.5],
      [180, 0, 0],
    ],
    [
      [4, 5, 6],
      [-95.5, -30.2, 170.4],
    ],
  ]) {
    const rows = withRotation(
      rotationXYZ(rotationDeg.map(THREE.MathUtils.degToRad)),
      translation,
    );
    const converted = ptzPoseToCameraMatrix(
      poseContext({ matrix: rows }),
      SCENE_ID,
      VERSION,
    );
    assert.ok(
      ptzMatricesClose(
        converted,
        storedPoseCameraMatrix(translation, rotationDeg),
      ),
      `pose ${rotationDeg}`,
    );
  }
});

test("poses that are not a usable stationary pose are rejected", () => {
  const malformed = (pose) => ({ ...poseContext(), pose });
  const cases = {
    "not valid": { ...poseContext(), valid: false },
    slewing: poseContext({ motionState: "slewing", valid: true }),
    settling: poseContext({ motionState: "settling" }),
    unknown: poseContext({ motionState: "unknown" }),
    "other calibration version": poseContext({ version: "cam-v2" }),
    "other scene": poseContext({ frameId: "scene:other" }),
    camera_from_scene: malformed({
      ...poseContext().pose,
      transform_direction: "camera_from_scene",
    }),
    "column major": malformed({
      ...poseContext().pose,
      matrix_layout: "column_major",
    }),
    "3x3 matrix": poseContext({
      matrix: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ],
    }),
    "non-finite value": poseContext({
      matrix: [[NaN, 0, 0, 0], ...HOME.slice(1)],
    }),
    "missing pose": malformed(undefined),
    "missing message": null,
  };
  for (const [name, message] of Object.entries(cases)) {
    assert.equal(ptzPoseToCameraMatrix(message, SCENE_ID, VERSION), null, name);
  }
});

test("malformed scene_from_camera matrices are rejected", () => {
  assert.equal(sceneFromCameraToCameraMatrix(null), null);
  assert.equal(sceneFromCameraToCameraMatrix([[1, 0, 0, 0]]), null);
  assert.equal(
    sceneFromCameraToCameraMatrix([[1, 0, 0, "x"], ...HOME.slice(1)]),
    null,
  );
  assert.ok(sceneFromCameraToCameraMatrix(HOME) instanceof THREE.Matrix4);
});

test("matrix comparison treats missing matrices as different", () => {
  const home = sceneFromCameraToCameraMatrix(HOME);
  assert.equal(ptzMatricesClose(null, null), false);
  assert.equal(ptzMatricesClose(home, null), false);
  assert.equal(ptzMatricesClose(home, home.clone()), true);
});

test("only slewing and settling count as moving", () => {
  assert.equal(isPTZMoving({ motion_state: "slewing" }), true);
  assert.equal(isPTZMoving({ motion_state: "settling" }), true);
  assert.equal(isPTZMoving({ motion_state: "stationary" }), false);
  assert.equal(isPTZMoving({ motion_state: "unknown" }), false);
  assert.equal(isPTZMoving(null), false);
});

test("away from home uses the configured angular tolerance", () => {
  const half = PTZ_HOME_ANGLE_TOLERANCE_RAD / 2;
  assert.equal(isPTZAwayFromHomePose(HOME, HOME), false);
  assert.equal(isPTZAwayFromHomePose(HOME, movedPose(half, half / 2)), false);
  assert.equal(
    isPTZAwayFromHomePose(HOME, movedPose(2 * PTZ_HOME_ANGLE_TOLERANCE_RAD)),
    true,
  );
  assert.equal(isPTZAwayFromHomePose(HOME, movedPose(0, -0.003)), true);
});

test("no point mapping is needed at the home pose", () => {
  for (const distortion of Object.values(LENSES)) {
    assert.equal(
      createPTZPointMapper(HOME, HOME, INTRINSICS, distortion),
      null,
    );
    assert.equal(
      createPTZPointMapper(HOME, movedPose(0.0002), INTRINSICS, distortion),
      null,
    );
  }
});

test("mapped home points match the projection at the live pose", () => {
  const [width, height] = IMAGE_SIZE;
  const [fx, fy, cx, cy] = INTRINSICS;
  const live = movedPose(0.22, -0.12);
  const inside = ([u, v]) => u >= 0 && u <= width && v >= 0 && v <= height;
  for (const [name, distortion] of Object.entries(LENSES)) {
    const mapper = createPTZPointMapper(HOME, live, INTRINSICS, distortion);
    let checked = 0;
    for (let u = 0; u <= width; u += width / 8) {
      for (let v = 0; v <= height; v += height / 6) {
        const ray = HOME.slice(0, 3).map(
          (row) => row[0] * ((u - cx) / fx) + row[1] * ((v - cy) / fy) + row[2],
        );
        const point = HOME.slice(0, 3).map((row, i) => row[3] + 6 * ray[i]);
        const atHome = project(HOME, point, distortion, INTRINSICS);
        const atLive = project(live, point, distortion, INTRINSICS);
        if (!atHome || !atLive || !inside(atHome) || !inside(atLive)) continue;
        const mapped = mapper(...atHome);
        assert.ok(mapped, `${name}: point ${atHome} hidden`);
        assert.ok(
          Math.hypot(mapped[0] - atLive[0], mapped[1] - atLive[1]) < 1e-4,
          `${name}: ${mapped} != ${atLive}`,
        );
        checked += 1;
      }
    }
    assert.ok(checked > 5, `${name}: only ${checked} points checked`);
  }
});

test("points behind the moved camera are hidden", () => {
  const mapper = createPTZPointMapper(
    HOME,
    movedPose(Math.PI),
    INTRINSICS,
    LENSES.none,
  );
  assert.equal(mapper(INTRINSICS[2], INTRINSICS[3]), null);
});

test("points beyond the distortion model fold-back are hidden", () => {
  const [width, height] = IMAGE_SIZE;
  const strongBarrel = [-0.45, 0.2, 0, 0, -0.05];
  const mapper = createPTZPointMapper(
    HOME,
    movedPose(1.3),
    INTRINSICS,
    strongBarrel,
  );
  for (let u = 0; u <= width; u += width / 16) {
    for (let v = 0; v <= height; v += height / 8) {
      const mapped = mapper(u, v);
      const inside =
        mapped &&
        mapped[0] >= 0 &&
        mapped[0] <= width &&
        mapped[1] >= 0 &&
        mapped[1] <= height;
      assert.ok(!inside, `home point ${u},${v} folded into the frame`);
    }
  }
});

test("missing distortion coefficients are treated as zero", () => {
  const live = movedPose(0.1);
  const missing = createPTZPointMapper(HOME, live, INTRINSICS, [
    NaN,
    undefined,
    "",
    null,
    0,
  ]);
  const none = createPTZPointMapper(HOME, live, INTRINSICS, LENSES.none);
  assert.deepEqual(missing(800, 600), none(800, 600));
});

test("retained poses past valid_until are rejected on receipt", () => {
  const now = Date.parse(isoAt(0));
  const accepted = (context) =>
    ptzPoseToCameraMatrix(context, SCENE_ID, VERSION, now) !== null;
  assert.equal(accepted(poseContext({ timestamp: isoAt(-0.1) })), true);
  assert.equal(
    accepted(poseContext({ timestamp: isoAt(-2) })),
    true,
    "within the browser clock skew tolerance",
  );
  assert.equal(accepted(poseContext({ timestamp: isoAt(-60) })), false);
  const withoutExpiry = poseContext();
  delete withoutExpiry.valid_until;
  assert.equal(accepted(withoutExpiry), false);
  assert.equal(isPTZPoseExpired(poseContext({ lifetimeMs: 0 }), now), true);
});

test("frame gate holds frames until the video shows the stopped camera", () => {
  const gate = new PTZFrameGate();
  const stopped = poseContext({ timestamp: isoAt(10) });
  assert.equal(gate.accepts(isoAt(0)), true, "no PTZ pose yet");

  gate.update(stopped, true, false);
  assert.equal(gate.accepts(isoAt(0)), true, "no move observed");

  gate.update(poseContext({ motionState: "slewing" }), false, true);
  assert.equal(gate.accepts(isoAt(20)), false, "moving");
  gate.update(stopped, true, false);
  const cutoff = 10 + PTZ_VIDEO_LATENCY_MS / 1000;
  assert.equal(gate.accepts(isoAt(cutoff - 0.01)), false);
  assert.equal(gate.accepts(isoAt(cutoff)), true);
  assert.equal(gate.accepts(undefined), true, "frames without a timestamp");

  gate.update(poseContext({ timestamp: isoAt(11) }), true, false);
  assert.equal(gate.accepts(isoAt(cutoff - 0.01)), false, "cutoff kept");

  gate.update(poseContext({ motionState: "unknown" }), false, false);
  assert.equal(gate.accepts(isoAt(0)), true, "home pose fallback");
});

test("frame gate rejects work started for an earlier pose", () => {
  const gate = new PTZFrameGate();
  const generation = gate.generation;
  assert.equal(gate.accepts(isoAt(0), generation), true);
  gate.invalidate();
  assert.equal(gate.accepts(isoAt(0), generation), false);
  assert.equal(gate.accepts(isoAt(0)), true);
});

test("a live pose expires unless a newer one arrives in its lifetime", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const expiry = new PTZPoseExpiry();
  const onExpire = spy();
  const live = poseContext({ lifetimeMs: 500 });

  expiry.arm(live, onExpire);
  t.mock.timers.tick(400);
  expiry.arm(live, onExpire);
  t.mock.timers.tick(400);
  assert.equal(onExpire.calls.length, 0, "re-armed by the newer pose");
  t.mock.timers.tick(100);
  assert.equal(onExpire.calls.length, 1);

  expiry.arm(live, onExpire);
  expiry.arm(null, onExpire);
  t.mock.timers.tick(1000);
  assert.equal(onExpire.calls.length, 1, "cancelled without a live pose");
});
