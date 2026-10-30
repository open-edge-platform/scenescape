// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import * as THREE from "/static/assets/three.module.js";
import { CSS2DObject } from "/static/examples/jsm/renderers/CSS2DRenderer.js";

const SELECTED_COLOR = 0xffff00;
const SOURCE_COLOR_SATURATION = 0.85;
const SOURCE_COLOR_LIGHTNESS = 0.58;
const GOLDEN_ANGLE_DEGREES = 137.508;
const NEAR = 0.2;
const FAR = 1;

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

function validCamera(camera) {
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

function validState(state, sceneID, sourceID) {
  if (
    !state ||
    state.scene_id !== sceneID ||
    state.source_id !== sourceID ||
    !pose(state) ||
    typeof state.timestamp !== "string" ||
    typeof state.expires_at !== "string" ||
    !Number.isFinite(Date.parse(state.timestamp)) ||
    !Number.isFinite(Date.parse(state.expires_at)) ||
    Date.parse(state.expires_at) < Date.parse(state.timestamp)
  ) {
    return false;
  }
  if (state.cameras !== undefined && !Array.isArray(state.cameras)) {
    return false;
  }
  const cameraIds = new Set();
  for (const camera of state.cameras || []) {
    if (!validCamera(camera) || cameraIds.has(camera.id)) return false;
    cameraIds.add(camera.id);
  }
  const intrinsics = state.intrinsics;
  return (
    intrinsics === undefined ||
    (["fx", "fy", "cx", "cy"].every((key) =>
      Number.isFinite(intrinsics?.[key]),
    ) &&
      intrinsics.fx > 0 &&
      intrinsics.fy > 0)
  );
}

function applyPose(object, state) {
  object.position.fromArray(state.translation);
  object.quaternion.fromArray(state.rotation).normalize();
}

function droneMarker(color) {
  const group = new THREE.Group();
  const material = new THREE.LineBasicMaterial({ color });
  const body = new THREE.BufferGeometry().setFromPoints(
    [
      [0.4, 0, 0],
      [-0.2, 0.2, 0],
      [-0.2, -0.2, 0],
    ].map((point) => new THREE.Vector3(...point)),
  );
  group.add(new THREE.LineLoop(body, material));
  const arms = new THREE.BufferGeometry().setFromPoints(
    [
      [-0.3, -0.3, 0],
      [0.3, 0.3, 0],
      [-0.3, 0.3, 0],
      [0.3, -0.3, 0],
    ].map((point) => new THREE.Vector3(...point)),
  );
  group.add(new THREE.LineSegments(arms, material));
  const rotor = new THREE.BufferGeometry().setFromPoints(
    new THREE.EllipseCurve(0, 0, 0.15, 0.15).getPoints(20),
  );
  for (const x of [-0.3, 0.3]) {
    for (const y of [-0.3, 0.3]) {
      const ring = new THREE.LineLoop(rotor, material);
      ring.position.set(x, y, 0);
      group.add(ring);
    }
  }
  return group;
}

function frustumPoints({ intrinsics }) {
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

export default class DynamicSources {
  constructor(scene, sceneID, onSelect = () => {}) {
    this.sceneID = sceneID;
    this.root = new THREE.Group();
    this.root.name = "dynamic-sources";
    scene.add(this.root);
    this.sources = new Map();
    this.usedColors = new Set();
    this.nextColorIndex = 0;
    this.showFrustums = true;
    this.selectedSource = null;
    this.onSelect = onSelect;
  }

  allocateColor() {
    let color;
    do {
      const hue = ((this.nextColorIndex++ * GOLDEN_ANGLE_DEGREES) % 360) / 360;
      color = new THREE.Color()
        .setHSL(hue, SOURCE_COLOR_SATURATION, SOURCE_COLOR_LIGHTNESS)
        .getHex();
    } while (this.usedColors.has(color));
    this.usedColors.add(color);
    return color;
  }

  handleMessage(sourceID, data, now = Date.now()) {
    if (!sourceID || sourceID.includes("/")) {
      console.warn("Invalid dynamic source topic", sourceID);
      return;
    }
    if (data.length === 0) {
      this.remove(sourceID);
      return;
    }
    let state;
    try {
      state = JSON.parse(data.toString());
    } catch (error) {
      console.warn("Invalid dynamic source JSON", sourceID, error);
      return;
    }
    if (!validState(state, this.sceneID, sourceID)) {
      console.warn("Invalid dynamic source state", sourceID);
      return;
    }
    const timestamp = Date.parse(state.timestamp);
    let entry = this.sources.get(sourceID);
    if (entry && timestamp < entry.timestamp) return;
    const expiresAt = Date.parse(state.expires_at);
    if (expiresAt <= now) {
      this.remove(sourceID);
      return;
    }
    if (!entry) {
      const color = this.allocateColor();
      const body = droneMarker(color);
      body.name = sourceID;
      body.userData.source_id = sourceID;
      const element = document.createElement("div");
      element.className = "asset-label visible";
      element.style.marginTop = "-32px";
      const label = new CSS2DObject(element);
      label.name = "source-label";
      label.center.set(0.5, 1);
      label.visible = false;
      body.add(label);
      this.root.add(body);
      entry = { body, cameras: new Map(), label, color };
      this.sources.set(sourceID, entry);
    }
    applyPose(entry.body, state);
    entry.timestamp = timestamp;
    entry.expiresAt = expiresAt;
    const cameras = new Map(
      (state.cameras || []).map((camera) => [camera.id, camera]),
    );
    for (const cameraID of entry.cameras.keys()) {
      if (!cameras.has(cameraID)) this.removeCamera(entry, cameraID);
    }
    for (const camera of cameras.values()) {
      let frustum = entry.cameras.get(camera.id);
      if (!frustum) {
        frustum = new THREE.LineSegments(
          new THREE.BufferGeometry(),
          new THREE.LineBasicMaterial({ color: entry.color }),
        );
        frustum.name = "source-camera-frustum";
        frustum.userData.sourceFrustum = true;
        frustum.userData.camera_id = camera.id;
        entry.body.add(frustum);
        entry.cameras.set(camera.id, frustum);
      }
      applyPose(frustum, camera.mount);
      frustum.geometry.setFromPoints(frustumPoints(camera));
      frustum.geometry.computeBoundingSphere();
      frustum.visible = this.showFrustums;
    }
    entry.hasCamera = entry.cameras.size > 0;
    entry.label.element.textContent = entry.hasCamera
      ? sourceID
      : `${sourceID} - FOV unavailable`;
  }

  removeCamera(entry, cameraID) {
    const frustum = entry.cameras.get(cameraID);
    if (!frustum) return;
    frustum.geometry.dispose();
    frustum.material.dispose();
    entry.body.remove(frustum);
    entry.cameras.delete(cameraID);
  }

  setFrustumsVisible(visible) {
    this.showFrustums = visible;
    for (const entry of this.sources.values()) {
      for (const frustum of entry.cameras.values()) {
        frustum.visible = visible;
      }
    }
  }

  setVisible(visible) {
    this.root.visible = visible;
    if (!visible) this.select(null);
  }

  select(sourceID) {
    if (sourceID !== null && !this.sources.has(sourceID)) return;
    if (sourceID === this.selectedSource) return;
    this.selectedSource = sourceID;
    for (const [id, entry] of this.sources) {
      entry.label.visible = id === sourceID;
      entry.body.traverse((object) => {
        if (object.material) {
          object.material.color.setHex(
            id === sourceID ? SELECTED_COLOR : entry.color,
          );
        }
      });
    }
    this.onSelect(sourceID);
  }

  selectFromIntersections(intersections) {
    if (!this.root.visible) return false;
    for (const { object } of intersections) {
      let body = object;
      while (body.parent && body.parent !== this.root) body = body.parent;
      const sourceID = body.userData.source_id;
      const entry = this.sources.get(sourceID);
      if (object.userData.sourceFrustum) continue;
      if (entry?.body === body && body.visible) {
        this.select(sourceID === this.selectedSource ? null : sourceID);
        return true;
      }
    }
    this.select(null);
    return false;
  }

  expire(now = Date.now()) {
    for (const [sourceID, entry] of this.sources) {
      if (entry.expiresAt <= now) this.remove(sourceID);
    }
  }

  remove(sourceID) {
    const entry = this.sources.get(sourceID);
    if (!entry) return;
    if (this.selectedSource === sourceID) this.select(null);
    const geometries = new Set();
    const materials = new Set();
    entry.body.traverse((object) => {
      if (object.geometry) geometries.add(object.geometry);
      if (object.material) materials.add(object.material);
    });
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    entry.label.element.remove();
    this.root.remove(entry.body);
    this.usedColors.delete(entry.color);
    this.sources.delete(sourceID);
  }

  clear() {
    for (const sourceID of this.sources.keys()) this.remove(sourceID);
  }
}
