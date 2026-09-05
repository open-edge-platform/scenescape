// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import * as THREE from "/static/assets/three.module.js";

const DEFAULT_POINT_SIZE = 0.12;
const DEFAULT_OPACITY = 0.85;
const INTENSITY_RANGE_SMOOTHING = 0.15;

/**
 * Decode a base64 xyz[+intensity] float32 payload into Float32Arrays.
 * @param {string} b64
 * @param {number} count
 * @param {number} stride - floats per point (3 or 4)
 * @returns {{positions: Float32Array, intensities: Float32Array|null}}
 */
export function decodePointCloudPayload(b64, count, stride = 4) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  const floats = new Float32Array(
    bytes.buffer,
    bytes.byteOffset,
    Math.floor(bytes.byteLength / 4),
  );
  const positions = new Float32Array(count * 3);
  const intensities = stride >= 4 ? new Float32Array(count) : null;
  for (let i = 0; i < count; i++) {
    const src = i * stride;
    const dst = i * 3;
    positions[dst] = floats[src];
    positions[dst + 1] = floats[src + 1];
    positions[dst + 2] = floats[src + 2];
    if (intensities) {
      intensities[i] = floats[src + 3];
    }
  }
  return { positions, intensities };
}

/**
 * Map intensity values to RGB colors using a stable (smoothed) value range.
 */
export function intensityToColors(intensities, rangeState) {
  const colors = new Float32Array(intensities.length * 3);
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < intensities.length; i++) {
    const v = intensities[i];
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    min = 0;
    max = 1;
  }
  if (rangeState.min == null || rangeState.max == null) {
    rangeState.min = min;
    rangeState.max = max;
  } else {
    rangeState.min =
      rangeState.min * (1 - INTENSITY_RANGE_SMOOTHING) +
      min * INTENSITY_RANGE_SMOOTHING;
    rangeState.max =
      rangeState.max * (1 - INTENSITY_RANGE_SMOOTHING) +
      max * INTENSITY_RANGE_SMOOTHING;
  }
  const range = Math.max(rangeState.max - rangeState.min, 1e-6);
  for (let i = 0; i < intensities.length; i++) {
    const t = (intensities[i] - rangeState.min) / range;
    const c = heatColor(t);
    colors[i * 3] = c[0];
    colors[i * 3 + 1] = c[1];
    colors[i * 3 + 2] = c[2];
  }
  return colors;
}

function heatColor(t) {
  // Simple blue → cyan → green → yellow → red heatmap
  const x = Math.min(1, Math.max(0, t));
  if (x < 0.25) {
    const u = x / 0.25;
    return [0, u, 1];
  }
  if (x < 0.5) {
    const u = (x - 0.25) / 0.25;
    return [0, 1, 1 - u];
  }
  if (x < 0.75) {
    const u = (x - 0.5) / 0.25;
    return [u, 1, 0];
  }
  const u = (x - 0.75) / 0.25;
  return [1, 1 - u, 0];
}

/**
 * Manage a THREE.Points cloud placed in scene world coordinates using a
 * SceneScape (y-down) sensor pose — matching tracked-object placement.
 *
 * Geometry/material are reused across frames to avoid flicker from destroy/create.
 */
export class PointCloudVisualizer {
  constructor(scene) {
    this.scene = scene;
    this.pointsObject = null;
    this.visible = false;
    this.pointSize = DEFAULT_POINT_SIZE;
    this.opacity = DEFAULT_OPACITY;
    this.lastPayload = null;
    this.intensityRange = { min: null, max: null };
    this.pose = {
      position: new THREE.Vector3(),
      rotation: new THREE.Euler(0, 0, 0, "XYZ"),
    };
    this._scratchMatrix = new THREE.Matrix4();
    this._scratchQuat = new THREE.Quaternion();
    this._scratchVec = new THREE.Vector3();
    this._worldPos = null;
  }

  setPoseFromYdown(position, rotationRadians) {
    this.pose.position.copy(position);
    this.pose.rotation.copy(rotationRadians);
    if (this.lastPayload && this.visible) {
      this.updateFromPayload(this.lastPayload);
    }
  }

  setVisible(visibility) {
    this.visible = visibility;
    if (this.pointsObject) {
      this.pointsObject.visible = visibility;
    }
    if (!visibility) {
      this.clear();
    }
  }

  setPointSize(size) {
    this.pointSize = size;
    if (this.pointsObject && this.pointsObject.material) {
      this.pointsObject.material.size = size;
    }
  }

  setOpacity(opacity) {
    this.opacity = opacity;
    if (this.pointsObject && this.pointsObject.material) {
      this.pointsObject.material.opacity = opacity;
    }
  }

  clear() {
    if (this.pointsObject) {
      this.scene.remove(this.pointsObject);
      this.pointsObject.geometry.dispose();
      this.pointsObject.material.dispose();
      this.pointsObject = null;
    }
    this._worldPos = null;
    this.intensityRange = { min: null, max: null };
  }

  updateFromPayload(payload) {
    if (!payload || !payload.points || !payload.count) {
      return;
    }
    this.lastPayload = payload;
    const stride = payload.stride || 4;
    const count = payload.count;
    const { positions: localPos, intensities } = decodePointCloudPayload(
      payload.points,
      count,
      stride,
    );

    const matrix = this._scratchMatrix;
    const quat = this._scratchQuat.setFromEuler(this.pose.rotation);
    matrix.compose(this.pose.position, quat, new THREE.Vector3(1, 1, 1));

    const needed = count * 3;
    if (!this._worldPos || this._worldPos.length < needed) {
      // Grow with headroom so varying frame sizes do not reallocate every update.
      this._worldPos = new Float32Array(
        Math.ceil(Math.max(needed, 4096) * 1.25),
      );
    }
    const worldPosView = this._worldPos.subarray(0, needed);
    const v = this._scratchVec;
    for (let i = 0; i < count; i++) {
      v.set(localPos[i * 3], localPos[i * 3 + 1], localPos[i * 3 + 2]);
      v.applyMatrix4(matrix);
      worldPosView[i * 3] = v.x;
      worldPosView[i * 3 + 1] = v.y;
      worldPosView[i * 3 + 2] = v.z;
    }

    const colors = intensities
      ? intensityToColors(intensities, this.intensityRange)
      : null;

    if (!this.pointsObject) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(new Float32Array(this._worldPos), 3),
      );
      geometry.getAttribute("position").array.set(worldPosView);
      geometry.getAttribute("position").needsUpdate = true;
      if (colors) {
        const colorBuf = new Float32Array(this._worldPos.length);
        colorBuf.set(colors);
        geometry.setAttribute("color", new THREE.BufferAttribute(colorBuf, 3));
      }
      geometry.setDrawRange(0, count);
      const material = new THREE.PointsMaterial({
        size: this.pointSize,
        sizeAttenuation: true,
        transparent: true,
        opacity: this.opacity,
        vertexColors: Boolean(colors),
        color: colors ? 0xffffff : 0x00e5ff,
        depthWrite: false,
      });
      this.pointsObject = new THREE.Points(geometry, material);
      this.pointsObject.name = "sensor-pointcloud";
      this.pointsObject.frustumCulled = false;
      this.scene.add(this.pointsObject);
    } else {
      const geometry = this.pointsObject.geometry;
      const posAttr = geometry.getAttribute("position");
      if (!posAttr || posAttr.array.length < needed) {
        geometry.setAttribute(
          "position",
          new THREE.BufferAttribute(new Float32Array(this._worldPos), 3),
        );
      }
      geometry.getAttribute("position").array.set(worldPosView);
      geometry.getAttribute("position").needsUpdate = true;
      if (colors) {
        let colorAttr = geometry.getAttribute("color");
        if (!colorAttr || colorAttr.array.length < colors.length) {
          const colorBuf = new Float32Array(
            Math.max(colors.length, this._worldPos.length),
          );
          geometry.setAttribute(
            "color",
            new THREE.BufferAttribute(colorBuf, 3),
          );
          colorAttr = geometry.getAttribute("color");
          this.pointsObject.material.vertexColors = true;
        }
        colorAttr.array.set(colors);
        colorAttr.needsUpdate = true;
      }
      geometry.setDrawRange(0, count);
      this.pointsObject.material.size = this.pointSize;
      this.pointsObject.material.opacity = this.opacity;
    }

    this.pointsObject.visible = this.visible;
  }
}

export default PointCloudVisualizer;
