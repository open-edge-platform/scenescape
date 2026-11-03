// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @module ptzpose
 * @description Display-only consumer of Positioning PTZ PoseContext messages.
 */

"use strict";

import * as THREE from "/static/assets/three.module.js";

const MATRIX_TOLERANCE = 1e-6;
// The browser clock is not NTP-disciplined like Positioning; allow this much skew
// before a retained PoseContext is treated as expired on receipt.
const PTZ_CLOCK_SKEW_TOLERANCE_MS = 2000;

/**
 * Lifetime of a PoseContext (valid_until - timestamp) in milliseconds.
 * @param {Object} msg - Parsed PoseContext payload.
 * @returns {number} Positive lifetime, or 0 when the timestamps are unusable.
 */
function ptzPoseLifetimeMs(msg) {
  const lifetime = Date.parse(msg?.valid_until) - Date.parse(msg?.timestamp);
  return Number.isFinite(lifetime) && lifetime > 0 ? lifetime : 0;
}

/**
 * Whether a PoseContext is already past its exclusive valid_until on receipt,
 * for example a retained pose left behind by a stopped Positioning service.
 * @param {Object} msg - Parsed PoseContext payload.
 * @param {number} now - Receipt time in milliseconds since the epoch.
 * @returns {boolean}
 */
function isPTZPoseExpired(msg, now = Date.now()) {
  if (ptzPoseLifetimeMs(msg) === 0) return true;
  return now - PTZ_CLOCK_SKEW_TOLERANCE_MS >= Date.parse(msg.valid_until);
}

/**
 * Converts a PoseContext into a three.js (y-up) camera matrix.
 * @param {Object} msg - Parsed PoseContext payload.
 * @param {string} sceneID - UID of the scene that owns the camera.
 * @param {string} calibrationVersion - PTZ calibration version known to the UI.
 * @param {number} now - Receipt time in milliseconds since the epoch.
 * @returns {THREE.Matrix4|null} The camera matrix, or null when the camera has no
 * usable stationary pose (moving, settling, expired, or for another
 * scene/calibration).
 */
function ptzPoseToCameraMatrix(
  msg,
  sceneID,
  calibrationVersion,
  now = Date.now(),
) {
  if (!msg || msg.valid !== true || msg.motion_state !== "stationary") {
    return null;
  }
  if (msg.calibration_version !== calibrationVersion) {
    return null;
  }
  if (isPTZPoseExpired(msg, now)) {
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
 * Decides which camera frames may be projected with the current PTZ pose.
 *
 * Frames are rejected while the camera moves, and after an observed move until
 * one is captured PTZ_VIDEO_LATENCY_MS after the first stationary pose, because
 * the video lags the pose. The generation changes whenever the displayed pose
 * changes, so asynchronous work (decoding, undistortion, texture loading)
 * started for an earlier pose can be rejected when it completes.
 */
class PTZFrameGate {
  constructor() {
    this.generation = 0;
    this.notBefore = -Infinity;
    this.motionSeen = false;
    this.stationary = false;
  }

  /**
   * @param {Object} msg - Parsed PoseContext payload.
   * @param {boolean} live - Whether msg is a usable live stationary pose.
   * @param {boolean} moving - Whether msg reports slewing or settling.
   */
  update(msg, live, moving) {
    if (moving) {
      this.motionSeen = true;
      this.stationary = false;
      this.notBefore = Infinity;
    } else if (!live) {
      // No live pose: the stored home pose is shown as for other cameras.
      this.stationary = false;
      this.notBefore = -Infinity;
    } else if (!this.stationary) {
      const poseTime = Date.parse(msg.timestamp);
      this.notBefore =
        this.motionSeen && Number.isFinite(poseTime)
          ? poseTime + PTZ_VIDEO_LATENCY_MS
          : -Infinity;
      this.motionSeen = false;
      this.stationary = true;
    }
  }

  invalidate() {
    this.generation += 1;
  }

  /**
   * @param {string} frameTimestamp - Acquisition timestamp of the frame.
   * @param {number} generation - Generation captured when the frame arrived.
   * @returns {boolean} Whether the frame may be projected.
   */
  accepts(frameTimestamp, generation = this.generation) {
    if (generation !== this.generation || this.notBefore === Infinity) {
      return false;
    }
    if (this.notBefore === -Infinity) return true;
    const frameTime = Date.parse(frameTimestamp);
    return !Number.isFinite(frameTime) || frameTime >= this.notBefore;
  }
}

/**
 * Expires a cached live pose when no newer one arrives within its lifetime, for
 * example when Positioning stops after publishing a valid retained pose.
 */
class PTZPoseExpiry {
  constructor() {
    this.timer = null;
  }

  /**
   * @param {Object|null} msg - Live PoseContext now displayed, or null for none.
   * @param {Function} onExpire - Called when msg expires without a successor.
   */
  arm(msg, onExpire) {
    clearTimeout(this.timer);
    this.timer = msg ? setTimeout(onExpire, ptzPoseLifetimeMs(msg)) : null;
  }
}

// Stands in for the PoseContext a consumer would see for an expired pose.
function expiredPTZPoseContext() {
  return {
    timestamp: new Date().toISOString(),
    valid: false,
    motion_state: "unknown",
    invalid_reason: "pose_expired",
    reason_detail: "sample_stale",
  };
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
  PTZFrameGate,
  PTZPoseExpiry,
  expiredPTZPoseContext,
  isPTZPoseExpired,
  ptzPoseLifetimeMs,
  ptzPoseToCameraMatrix,
  sceneFromCameraToCameraMatrix,
  ptzMatricesClose,
  createPTZPointMapper,
  isPTZAwayFromHomePose,
  isPTZMoving,
};
