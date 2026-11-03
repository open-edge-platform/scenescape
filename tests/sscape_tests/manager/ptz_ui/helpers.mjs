// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Shared PTZ fixtures for the Manager UI module tests. */

// Home pose (scene_from_camera, y-down camera) and intrinsics of a lab PTZ camera.
export const HOME = [
  [
    0.7788635136603029, -0.37430858727997735, 0.5032541192848741,
    3.3839097433485636,
  ],
  [
    -0.6271580955830038, -0.45627910719390974, 0.6312543857138961,
    0.6304912707930127,
  ],
  [
    -0.006659597091898781, -0.8072809039156048, -0.5901298093977098,
    2.6314051115893564,
  ],
  [0, 0, 0, 1],
];
export const INTRINSICS = [2373.6251, 2373.6251, 1344, 756];
export const IMAGE_SIZE = [2688, 1512];
export const SCENE_ID = "scene-uid";
export const VERSION = "cam-v1";

export function multiply(a, b) {
  return a.map((row) =>
    b[0].map((_, j) => row.reduce((sum, value, k) => sum + value * b[k][j], 0)),
  );
}

export function transpose(m) {
  return m[0].map((_, column) => m.map((row) => row[column]));
}

export function rotationXYZ([x, y, z]) {
  const rx = [
    [1, 0, 0],
    [0, Math.cos(x), -Math.sin(x)],
    [0, Math.sin(x), Math.cos(x)],
  ];
  const ry = [
    [Math.cos(y), 0, Math.sin(y)],
    [0, 1, 0],
    [-Math.sin(y), 0, Math.cos(y)],
  ];
  const rz = [
    [Math.cos(z), -Math.sin(z), 0],
    [Math.sin(z), Math.cos(z), 0],
    [0, 0, 1],
  ];
  return multiply(multiply(rx, ry), rz);
}

export function withRotation(rotation, translation) {
  return [
    [...rotation[0], translation[0]],
    [...rotation[1], translation[1]],
    [...rotation[2], translation[2]],
    [0, 0, 0, 1],
  ];
}

/** Home pose turned by pan (camera y) and tilt (camera x), as a PTZ move does. */
export function movedPose(panRad, tiltRad = 0) {
  const home = HOME.slice(0, 3).map((row) => row.slice(0, 3));
  const turn = multiply(
    rotationXYZ([0, panRad, 0]),
    rotationXYZ([tiltRad, 0, 0]),
  );
  return withRotation(
    multiply(home, turn),
    HOME.slice(0, 3).map((row) => row[3]),
  );
}

export function poseContext({
  matrix = HOME,
  motionState = "stationary",
  valid = motionState === "stationary",
  timestamp = new Date().toISOString(),
  lifetimeMs = 500,
  version = VERSION,
  frameId = `scene:${SCENE_ID}`,
} = {}) {
  const context = {
    timestamp,
    valid_until: new Date(Date.parse(timestamp) + lifetimeMs).toISOString(),
    valid,
    motion_state: motionState,
    calibration_version: version,
  };
  if (valid) {
    context.pose = {
      frame_id: frameId,
      transform_direction: "scene_from_camera",
      matrix_layout: "row_major",
      matrix_4x4: matrix,
    };
  }
  return context;
}

/** OpenCV projectPoints of a scene point; null when behind the camera. */
export function project(pose, point, [k1, k2, p1, p2, k3], [fx, fy, cx, cy]) {
  const rotation = pose.slice(0, 3).map((row) => row.slice(0, 3));
  const offset = point.map((value, i) => value - pose[i][3]);
  const camera = transpose(rotation).map((row) =>
    row.reduce((sum, value, k) => sum + value * offset[k], 0),
  );
  if (camera[2] <= 0) return null;
  const x = camera[0] / camera[2];
  const y = camera[1] / camera[2];
  const r2 = x * x + y * y;
  const radial = 1 + r2 * (k1 + r2 * (k2 + r2 * k3));
  return [
    fx * (x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)) + cx,
    fy * (y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y) + cy,
  ];
}

// Test times are relative to the real clock, because received poses are checked
// for expiry against it.
const BASE_TIME_MS = Date.now();

export function isoAt(seconds) {
  return new Date(BASE_TIME_MS + seconds * 1000).toISOString();
}

export function spy(implementation = () => undefined) {
  const fn = (...args) => {
    fn.calls.push(args);
    return implementation(...args);
  };
  fn.calls = [];
  return fn;
}
