// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

/** Hard cap on points accepted from an untrusted MQTT payload. */
export const MAX_POINT_CLOUD_POINTS = 100000;

/**
 * Maximum decoded byte length for a given stride (float32 = 4 bytes).
 * Reject oversized base64 payloads before allocating typed arrays.
 * @param {number} stride
 * @returns {number}
 */
export function maxDecodedBytes(stride) {
  return MAX_POINT_CLOUD_POINTS * stride * 4;
}

/**
 * Decode a base64 xyz[+intensity] float32 payload into Float32Arrays.
 * Validates stride, rejects oversized decoded buffers, and clamps count to
 * the decoded buffer and MAX_POINT_CLOUD_POINTS.
 * @param {string} b64
 * @param {number} count
 * @param {number} stride - floats per point (3 or 4)
 * @returns {{positions: Float32Array, intensities: Float32Array|null}|null}
 */
export function decodePointCloudPayload(b64, count, stride = 4) {
  if (stride !== 3 && stride !== 4) {
    return null;
  }
  if (typeof b64 !== "string" || !b64) {
    return null;
  }
  const requested = Number(count);
  if (!Number.isFinite(requested) || requested <= 0) {
    return null;
  }

  let binary;
  try {
    binary = atob(b64);
  } catch {
    return null;
  }
  // Bound decoded size before allocating aligned buffers (count clamp alone
  // does not stop a huge points string with a small claimed count).
  if (binary.length > maxDecodedBytes(stride) || binary.length % 4 !== 0) {
    return null;
  }

  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  // Copy into an aligned buffer — Uint8Array from atob may share a larger
  // ArrayBuffer whose byteOffset is not a multiple of 4.
  const aligned = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(aligned).set(bytes);
  const floats = new Float32Array(aligned);
  const fromBytes = Math.floor(floats.length / stride);
  const safeCount = Math.min(
    Math.floor(requested),
    fromBytes,
    MAX_POINT_CLOUD_POINTS,
  );
  if (safeCount <= 0) {
    return null;
  }

  const positions = new Float32Array(safeCount * 3);
  const intensities = stride >= 4 ? new Float32Array(safeCount) : null;
  for (let i = 0; i < safeCount; i++) {
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
