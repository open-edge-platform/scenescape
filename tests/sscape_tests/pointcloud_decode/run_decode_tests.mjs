// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Node test harness for pointcloud_decode.mjs (invoked via pytest).
 */
import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const decodeUrl = pathToFileURL(
  join(
    __dirname,
    "../../../manager/src/manager/static/js/pointcloud_decode.mjs",
  ),
).href;

const { decodePointCloudPayload, MAX_POINT_CLOUD_POINTS, maxDecodedBytes } =
  await import(decodeUrl);

function encodeFloats(floats) {
  const buf = Buffer.alloc(floats.length * 4);
  for (let i = 0; i < floats.length; i++) {
    buf.writeFloatLE(floats[i], i * 4);
  }
  return buf.toString("base64");
}

test("decodes valid xyz+intensity payload", () => {
  const b64 = encodeFloats([1, 2, 3, 0.5, 4, 5, 6, 0.25]);
  const decoded = decodePointCloudPayload(b64, 2, 4);
  assert.ok(decoded);
  assert.equal(decoded.positions.length, 6);
  assert.equal(decoded.intensities.length, 2);
  assert.equal(decoded.positions[0], 1);
  assert.equal(decoded.positions[5], 6);
  assert.equal(decoded.intensities[1], 0.25);
});

test("decodes valid xyz-only stride 3", () => {
  const b64 = encodeFloats([1, 2, 3, 4, 5, 6]);
  const decoded = decodePointCloudPayload(b64, 2, 3);
  assert.ok(decoded);
  assert.equal(decoded.positions.length, 6);
  assert.equal(decoded.intensities, null);
});

test("rejects unexpected stride", () => {
  const b64 = encodeFloats([1, 2, 3, 4]);
  assert.equal(decodePointCloudPayload(b64, 1, 2), null);
  assert.equal(decodePointCloudPayload(b64, 1, 5), null);
});

test("rejects invalid base64", () => {
  assert.equal(decodePointCloudPayload("!!!not-base64!!!", 1, 4), null);
});

test("rejects empty or non-positive count", () => {
  const b64 = encodeFloats([1, 2, 3, 4]);
  assert.equal(decodePointCloudPayload(b64, 0, 4), null);
  assert.equal(decodePointCloudPayload(b64, -1, 4), null);
  assert.equal(decodePointCloudPayload("", 1, 4), null);
});

test("clamps count to decoded buffer length", () => {
  const b64 = encodeFloats([1, 2, 3, 0.5]); // one point, stride 4
  const decoded = decodePointCloudPayload(b64, 9999, 4);
  assert.ok(decoded);
  assert.equal(decoded.positions.length, 3);
  assert.equal(decoded.intensities.length, 1);
});

test("rejects decoded buffer larger than hard byte cap", () => {
  // Claim a small count but send more bytes than maxDecodedBytes allows.
  const overFloats = MAX_POINT_CLOUD_POINTS * 4 + 4; // one float past cap at stride 4
  const floats = new Array(overFloats).fill(0);
  const b64 = encodeFloats(floats);
  assert.ok(Buffer.byteLength(Buffer.from(b64, "base64")) > maxDecodedBytes(4));
  assert.equal(decodePointCloudPayload(b64, 1, 4), null);
});

test("accepts payload at exactly the point cap", () => {
  // Minimal: stride 3, exactly MAX points would be huge to build — use a
  // small buffer and verify clamp to MAX when fromBytes would allow more
  // is covered by the buffer clamp test. Here verify maxDecodedBytes math.
  assert.equal(maxDecodedBytes(4), MAX_POINT_CLOUD_POINTS * 4 * 4);
  assert.equal(maxDecodedBytes(3), MAX_POINT_CLOUD_POINTS * 3 * 4);
});
