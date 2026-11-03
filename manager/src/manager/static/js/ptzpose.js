// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @module ptzpose
 * @description Display-only consumer of Positioning PTZ PoseContext messages.
 */

"use strict";

import * as THREE from "/static/assets/three.module.js";

const MATRIX_TOLERANCE = 1e-6;

/**
 * Converts a PoseContext into a three.js (y-up) camera matrix.
 * @param {Object} msg - Parsed PoseContext payload.
 * @param {string} sceneID - UID of the scene that owns the camera.
 * @param {string} calibrationVersion - PTZ calibration version known to the UI.
 * @returns {THREE.Matrix4|null} The camera matrix, or null when the camera has no
 * usable stationary pose (moving, settling, stale, or for another scene/calibration).
 */
function ptzPoseToCameraMatrix(msg, sceneID, calibrationVersion) {
  if (!msg || msg.valid !== true || msg.motion_state !== "stationary") {
    return null;
  }
  if (msg.calibration_version !== calibrationVersion) {
    return null;
  }
  const pose = msg.pose;
  if (
    !pose ||
    pose.frame_id !== `scene:${sceneID}` ||
    pose.transform_direction !== "scene_from_camera" ||
    pose.matrix_layout !== "row_major"
  ) {
    return null;
  }
  return sceneFromCameraToCameraMatrix(pose.matrix_4x4);
}

/**
 * Converts a row-major scene_from_camera 4x4 matrix (y-down camera, as in
 * PoseContext and the Manager pose_matrix) into a three.js (y-up) camera matrix.
 * @param {number[][]} rows - 4x4 matrix.
 * @returns {THREE.Matrix4|null} The camera matrix, or null when malformed.
 */
function sceneFromCameraToCameraMatrix(rows) {
  if (
    !Array.isArray(rows) ||
    rows.length !== 4 ||
    rows.some((row) => !Array.isArray(row) || row.length !== 4)
  ) {
    return null;
  }
  const flat = rows.flat().map(Number);
  if (!flat.every(Number.isFinite)) {
    return null;
  }

  const camera = new THREE.Object3D();
  new THREE.Matrix4()
    .set(...flat)
    .decompose(camera.position, camera.quaternion, camera.scale);
  // Positioning poses use the y-down camera convention; three.js cameras are y-up.
  camera.rotateY(Math.PI);
  camera.rotateZ(Math.PI);
  camera.updateMatrix();
  return camera.matrix;
}

function ptzMatricesClose(a, b) {
  return (
    a !== null &&
    b !== null &&
    a.elements.every(
      (value, i) => Math.abs(value - b.elements[i]) <= MATRIX_TOLERANCE,
    )
  );
}

// Below this pan/tilt offset from home, image points are used as stored.
const PTZ_HOME_ANGLE_TOLERANCE_RAD = 1e-3;
// Frame timestamps are post-decode; camera encoding and streaming latency is not in
// them. Margin for that latency before frames are treated as captured after a stop.
const PTZ_VIDEO_LATENCY_MS = 500;
const UNDISTORT_ITERATIONS = 50;
const UNDISTORT_TOLERANCE = 1e-9;

function rotationBlock(matrix4x4) {
  return matrix4x4.slice(0, 3).map((row) => row.slice(0, 3).map(Number));
}

// R_live^T * R_home maps home camera rays into the live camera.
function relativeRotation(homeMatrix, liveMatrix) {
  const home = rotationBlock(homeMatrix);
  const live = rotationBlock(liveMatrix);
  return [0, 1, 2].map((i) =>
    [0, 1, 2].map((j) =>
      [0, 1, 2].reduce((s, k) => s + live[k][i] * home[k][j], 0),
    ),
  );
}

const PTZ_AWAY_MESSAGE =
  "Move the PTZ camera to its home position and wait until it stops. " +
  "Calibration and pose are stored for the home position.";

/**
 * Whether the live pose is rotated away from the stored home pose.
 * @param {number[][]} homeMatrix - Stored home scene_from_camera 4x4 matrix.
 * @param {number[][]} liveMatrix - Live PoseContext scene_from_camera 4x4 matrix.
 * @returns {boolean}
 */
function isPTZAwayFromHomePose(homeMatrix, liveMatrix) {
  const r = relativeRotation(homeMatrix, liveMatrix);
  const cosAngle = (r[0][0] + r[1][1] + r[2][2] - 1) / 2;
  return cosAngle < Math.cos(PTZ_HOME_ANGLE_TOLERANCE_RAD);
}

// Moving and settling cameras are treated as away from home.
function isPTZMoving(msg) {
  return (
    !!msg && (msg.motion_state === "slewing" || msg.motion_state === "settling")
  );
}

// OpenCV distortion model with [k1, k2, p1, p2, k3] on normalized coordinates.
function distortNormalized([x, y], [k1, k2, p1, p2, k3]) {
  const r2 = x * x + y * y;
  const radial = 1 + r2 * (k1 + r2 * (k2 + r2 * k3));
  return [
    x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x),
    y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y,
  ];
}

// Inverse of distortNormalized by Newton's method; null if it does not converge.
function undistortNormalized(distorted, distortion) {
  const [k1, k2, p1, p2, k3] = distortion;
  let [x, y] = distorted;
  for (let i = 0; i < UNDISTORT_ITERATIONS; i++) {
    const [dx, dy] = distortNormalized([x, y], distortion);
    const ex = dx - distorted[0];
    const ey = dy - distorted[1];
    if (Math.hypot(ex, ey) <= UNDISTORT_TOLERANCE) {
      return [x, y];
    }
    const r2 = x * x + y * y;
    const radial = 1 + r2 * (k1 + r2 * (k2 + r2 * k3));
    const dRadial = k1 + r2 * (2 * k2 + 3 * k3 * r2);
    const jxx = radial + 2 * x * x * dRadial + 2 * p1 * y + 6 * p2 * x;
    const jxy = 2 * x * y * dRadial + 2 * p1 * x + 2 * p2 * y;
    const jyy = radial + 2 * y * y * dRadial + 6 * p1 * y + 2 * p2 * x;
    const det = jxx * jyy - jxy * jxy;
    if (!Number.isFinite(det) || Math.abs(det) < 1e-12) return null;
    x -= (jyy * ex - jxy * ey) / det;
    y -= (jxx * ey - jxy * ex) / det;
  }
  return null;
}

/**
 * Builds a display-only mapping of image points placed at the PTZ home pose into the
 * image at the live pose. Pan/tilt only rotates the camera, so a point is undistorted,
 * rotated by R_live^T * R_home, and distorted again.
 * @param {number[][]} homeMatrix - Stored home scene_from_camera 4x4 matrix.
 * @param {number[][]} liveMatrix - Live PoseContext scene_from_camera 4x4 matrix.
 * @param {number[]} intrinsics - [fx, fy, cx, cy] in pixels.
 * @param {number[]} distortion - [k1, k2, p1, p2, k3].
 * @returns {Function|null} (x, y) => [x, y] or null when the point is not visible, or
 * null when the camera is at its home pose.
 */
function createPTZPointMapper(homeMatrix, liveMatrix, intrinsics, distortion) {
  if (!isPTZAwayFromHomePose(homeMatrix, liveMatrix)) {
    return null;
  }
  const relative = relativeRotation(homeMatrix, liveMatrix);
  const [fx, fy, cx, cy] = intrinsics.map(Number);
  const coefficients = distortion.map((value) => Number(value) || 0);
  return (x, y) => {
    const ray = undistortNormalized(
      [(x - cx) / fx, (y - cy) / fy],
      coefficients,
    );
    if (ray === null) return null;
    const rotated = relative.map(
      (row) => row[0] * ray[0] + row[1] * ray[1] + row[2],
    );
    if (!(rotated[2] > 0)) return null;
    const normalized = [rotated[0] / rotated[2], rotated[1] / rotated[2]];
    const distorted = distortNormalized(normalized, coefficients);
    // Outside the model's valid range distortion folds back; such points are hidden.
    const roundTrip = undistortNormalized(distorted, coefficients);
    if (
      roundTrip === null ||
      Math.hypot(roundTrip[0] - normalized[0], roundTrip[1] - normalized[1]) >
        1e-6
    ) {
      return null;
    }
    return [fx * distorted[0] + cx, fy * distorted[1] + cy];
  };
}

export {
  PTZ_AWAY_MESSAGE,
  PTZ_HOME_ANGLE_TOLERANCE_RAD,
  PTZ_VIDEO_LATENCY_MS,
  ptzPoseToCameraMatrix,
  sceneFromCameraToCameraMatrix,
  ptzMatricesClose,
  createPTZPointMapper,
  isPTZAwayFromHomePose,
  isPTZMoving,
};
