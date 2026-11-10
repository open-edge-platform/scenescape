// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import * as THREE from "/static/assets/three.module.js";

const NEAR = 0.2;
const FAR = 1;
const DEFAULT_FRUSTUM_COLOR = 0x4fc3f7;
const FRUSTUM_NAME = "platform-camera-frustum";

function vector(value, length) {
  return (
    Array.isArray(value) &&
    value.length === length &&
    value.every(Number.isFinite)
  );
}

function pose(value) {
  return (
    vector(value?.translation, 3) &&
    vector(value?.rotation, 4) &&
    Number.isFinite(Math.hypot(...value.rotation)) &&
    Math.hypot(...value.rotation) > 0
  );
}

export function validPlatformCamera(camera) {
  const intrinsics = camera?.intrinsics;
  return (
    typeof camera?.id === "string" &&
    camera.id.length > 0 &&
    pose(camera.mount) &&
    ["fx", "fy", "cx", "cy"].every((key) =>
      Number.isFinite(intrinsics?.[key]),
    ) &&
    intrinsics.fx > 0 &&
    intrinsics.fy > 0
  );
}

export function frustumPoints({ intrinsics }) {
  const { fx, fy, cx, cy } = intrinsics;
  // Optical axes are x-right, y-down, z-forward, not Three.js camera axes.
  // Without image bounds, assume the principal point is centered.
  const corners = (depth) =>
    [
      [-cx, -cy],
      [cx, -cy],
      [cx, cy],
      [-cx, cy],
    ].map(
      ([x, y]) => new THREE.Vector3((x * depth) / fx, (y * depth) / fy, depth),
    );
  const near = corners(NEAR);
  const far = corners(FAR);
  const points = [];
  for (let i = 0; i < 4; i++) {
    const next = (i + 1) % 4;
    points.push(near[i], near[next], far[i], far[next], near[i], far[i]);
  }
  return points;
}

function applyPose(object, mount) {
  object.position.fromArray(mount.translation);
  object.quaternion.fromArray(mount.rotation).normalize();
}

function frustumMap(body) {
  const byId = new Map();
  for (const child of body.children) {
    if (child.name === FRUSTUM_NAME && child.userData.camera_id) {
      byId.set(child.userData.camera_id, child);
    }
  }
  return byId;
}

function disposeFrustum(body, frustum) {
  frustum.geometry.dispose();
  frustum.material.dispose();
  body.remove(frustum);
}

/**
 * Sync child frustums under a platform body mark from object-graph cameras[].
 * Expiry is driven by mark removal (regulated object absence), not MQTT retain.
 */
export function syncPlatformFrustums(
  body,
  cameras,
  { color = DEFAULT_FRUSTUM_COLOR, visible = true } = {},
) {
  const next = new Map();
  for (const camera of cameras || []) {
    if (!validPlatformCamera(camera) || next.has(camera.id)) continue;
    next.set(camera.id, camera);
  }
  const existing = frustumMap(body);
  for (const [cameraId, frustum] of existing) {
    if (!next.has(cameraId)) disposeFrustum(body, frustum);
  }
  for (const camera of next.values()) {
    let frustum = existing.get(camera.id);
    if (!frustum) {
      frustum = new THREE.LineSegments(
        new THREE.BufferGeometry(),
        new THREE.LineBasicMaterial({ color }),
      );
      frustum.name = FRUSTUM_NAME;
      frustum.userData.platformFrustum = true;
      frustum.userData.camera_id = camera.id;
      body.add(frustum);
    } else if (frustum.material?.color) {
      frustum.material.color.setHex(color);
    }
    applyPose(frustum, camera.mount);
    frustum.geometry.setFromPoints(frustumPoints(camera));
    frustum.geometry.computeBoundingSphere();
    frustum.visible = visible;
  }
  return next.size;
}

export function clearPlatformFrustums(body) {
  for (const frustum of frustumMap(body).values()) {
    disposeFrustum(body, frustum);
  }
}

export function setPlatformFrustumsVisible(body, visible) {
  for (const frustum of frustumMap(body).values()) {
    frustum.visible = visible;
  }
}
