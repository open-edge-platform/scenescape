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
  const rows = pose.matrix_4x4;
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

export { ptzPoseToCameraMatrix, ptzMatricesClose };
