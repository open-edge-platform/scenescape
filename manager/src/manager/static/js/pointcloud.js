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
  // Copy into an aligned buffer — Uint8Array from atob may share a larger
  // ArrayBuffer whose byteOffset is not a multiple of 4.
  const aligned = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(aligned).set(bytes);
  const floats = new Float32Array(aligned);
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
    if (!Number.isFinite(v)) continue;
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
    const raw = Number.isFinite(intensities[i]) ? intensities[i] : rangeState.min;
    const t = (raw - rangeState.min) / range;
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
 * Manage a THREE.Points cloud placed in scene world coordinates using the
 * sensor's THREE camera (y-up / OpenGL). Sensor-local points are SceneScape /
 * OpenCV (y-down) and converted with (x, -y, -z) before matrixWorld.
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
    this._scratchMatrix = new THREE.Matrix4();
    this._scratchVec = new THREE.Vector3();
    this._scaleOne = new THREE.Vector3(1, 1, 1);
    this._worldPos = null;
  }

  /**
   * Capture the sensor camera's current world transform for the next update.
   * @param {THREE.Object3D} camera
   */
  setPoseFromCamera(camera) {
    if (!camera) return;
    camera.updateWorldMatrix(true, false);
    this._scratchMatrix.copy(camera.matrixWorld);
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
    this._keptIntensity = null;
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
    const needed = count * 3;
    if (!this._worldPos || this._worldPos.length < needed) {
      // Grow with headroom so varying frame sizes do not reallocate every update.
      this._worldPos = new Float32Array(
        Math.ceil(Math.max(needed, 4096) * 1.25),
      );
    }
    if (intensities && (!this._keptIntensity || this._keptIntensity.length < count)) {
      this._keptIntensity = new Float32Array(
        Math.ceil(Math.max(count, 1024) * 1.25),
      );
    }
    const v = this._scratchVec;
    let written = 0;
    for (let i = 0; i < count; i++) {
      const lx = localPos[i * 3];
      const ly = localPos[i * 3 + 1];
      const lz = localPos[i * 3 + 2];
      if (!Number.isFinite(lx) || !Number.isFinite(ly) || !Number.isFinite(lz)) {
        continue;
      }
      // OpenCV / SceneScape sensor frame -> OpenGL local (THREE camera).
      v.set(lx, -ly, -lz);
      v.applyMatrix4(matrix);
      if (!Number.isFinite(v.x) || !Number.isFinite(v.y) || !Number.isFinite(v.z)) {
        continue;
      }
      const dst = written * 3;
      this._worldPos[dst] = v.x;
      this._worldPos[dst + 1] = v.y;
      this._worldPos[dst + 2] = v.z;
      if (intensities) {
        this._keptIntensity[written] = intensities[i];
      }
      written++;
    }
    if (written === 0) {
      return;
    }

    const worldPosExact = this._worldPos.subarray(0, written * 3);
    const colors = intensities
      ? intensityToColors(
          this._keptIntensity.subarray(0, written),
          this.intensityRange,
        )
      : null;

    if (!this.pointsObject) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(worldPosExact.slice(), 3),
      );
      if (colors) {
        geometry.setAttribute(
          "color",
          new THREE.BufferAttribute(colors.slice(0, written * 3), 3),
        );
      }
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
      let posAttr = geometry.getAttribute("position");
      if (!posAttr || posAttr.array.length < written * 3) {
        posAttr = new THREE.BufferAttribute(
          new Float32Array(
            Math.ceil(Math.max(written * 3, 4096) * 1.25),
          ),
          3,
        );
        geometry.setAttribute("position", posAttr);
      }
      posAttr.array.set(worldPosExact);
      posAttr.needsUpdate = true;
      posAttr.count = written;
      if (colors) {
        let colorAttr = geometry.getAttribute("color");
        if (!colorAttr || colorAttr.array.length < written * 3) {
          colorAttr = new THREE.BufferAttribute(
            new Float32Array(
              Math.ceil(Math.max(written * 3, 4096) * 1.25),
            ),
            3,
          );
          geometry.setAttribute("color", colorAttr);
          this.pointsObject.material.vertexColors = true;
        }
        colorAttr.array.set(colors.subarray(0, written * 3));
        colorAttr.needsUpdate = true;
        colorAttr.count = written;
      }
      this.pointsObject.material.size = this.pointSize;
      this.pointsObject.material.opacity = this.opacity;
    }

    const geometry = this.pointsObject.geometry;
    geometry.setDrawRange(0, written);
    geometry.computeBoundingSphere();
    this.pointsObject.visible = this.visible;
  }
}

export default PointCloudVisualizer;
