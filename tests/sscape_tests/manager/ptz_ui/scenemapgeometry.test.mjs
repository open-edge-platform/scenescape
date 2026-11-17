// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";

const { basePlaneLayout, unionBounds, hybridFrameSize } =
  await import("/static/js/thing/scenemapgeometry.js");

const box = (minX, minY, maxX, maxY) => ({
  min: { x: minX, y: minY, z: 0 },
  max: { x: maxX, y: maxY, z: 0 },
});

test("base plane size is image pixels divided by base_scale", () => {
  const layout = basePlaneLayout(1000, 500, 100);
  assert.equal(layout.width, 10);
  assert.equal(layout.height, 5);
});

test("base plane centre is half its size so the SW corner sits at the origin", () => {
  const layout = basePlaneLayout(1000, 500, 100);
  assert.equal(layout.centerX, 5);
  assert.equal(layout.centerY, 2.5);
});

test("union covers both boxes on every axis", () => {
  const union = unionBounds(box(0, 0, 4, 2), box(-1, 1, 3, 9));
  assert.deepEqual(union.min, { x: -1, y: 0, z: 0 });
  assert.deepEqual(union.max, { x: 4, y: 9, z: 0 });
});

test("union with a box inside the other returns the outer box", () => {
  const union = unionBounds(box(0, 0, 10, 10), box(2, 2, 3, 3));
  assert.deepEqual(union.min, { x: 0, y: 0, z: 0 });
  assert.deepEqual(union.max, { x: 10, y: 10, z: 0 });
});

test("hybrid frame uses the union width along X and height along Y", () => {
  const frame = hybridFrameSize(box(0, 0, 4, 2), box(0, 0, 10, 5));
  assert.equal(frame.floorWidth, 10);
  assert.equal(frame.floorHeight, 5);
});

test("hybrid frame grows when the GLB extends past the plane", () => {
  const frame = hybridFrameSize(box(-2, 0, 12, 8), box(0, 0, 10, 5));
  assert.equal(frame.floorWidth, 14);
  assert.equal(frame.floorHeight, 8);
});
