// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";

import { spy } from "./helpers.mjs";

class FakeImage {
  constructor() {
    this.complete = false;
    this.naturalWidth = 0;
    this.width = 0;
    this.height = 0;
  }

  set src(value) {
    this._src = value;
    this.complete = false;
  }

  get src() {
    return this._src;
  }
}
globalThis.Image = FakeImage;

const { CamCanvas } = await import("/static/js/camcanvas.js");

function makeCanvas() {
  const context = new Proxy({}, { get: () => () => undefined });
  const htmlCanvas = {
    width: 100,
    height: 100,
    clientWidth: 100,
    getContext: () => context,
    addEventListener() {},
    getBoundingClientRect: () => ({ left: 0, top: 0 }),
  };
  const canvas = new CamCanvas(htmlCanvas, "data:image/jpeg;base64,");
  canvas.image.width = 100;
  canvas.image.height = 100;
  canvas.calibrationPointSize = 10;
  canvas.calibrationPoints = [
    { x: 10, y: 20, color: "red", name: "p0" },
    { x: 30, y: 40, color: "blue", name: "p1" },
  ];
  canvas.drawPoint = spy();
  return canvas;
}

const drawnPositions = (canvas) =>
  canvas.drawPoint.calls.map(([x, y, , name]) => [name, x, y]);
const mouse = (x, y) => ({ clientX: x, clientY: y, preventDefault() {} });

test("stored points are drawn as stored without a mapper", () => {
  const canvas = makeCanvas();
  canvas.drawImage();
  assert.deepEqual(drawnPositions(canvas), [
    ["p0", 10, 20],
    ["p1", 30, 40],
  ]);
});

test("a mapper moves drawn points without changing stored points", () => {
  const canvas = makeCanvas();
  canvas.pointMapper = (x, y) => (x === 30 ? null : [x + 5, y + 7]);
  canvas.drawImage();
  assert.deepEqual(drawnPositions(canvas), [["p0", 15, 27]]);
  assert.deepEqual(
    canvas.calibrationPoints.map(({ x, y }) => [x, y]),
    [
      [10, 20],
      [30, 40],
    ],
  );
});

test("hidden points are not drawn", () => {
  const canvas = makeCanvas();
  canvas.pointsVisible = false;
  canvas.drawImage();
  assert.equal(canvas.drawPoint.calls.length, 0);
});

test("points are locked while mapped or hidden", () => {
  const canvas = makeCanvas();
  assert.equal(canvas.arePointsLocked(), false);
  canvas.pointMapper = (x, y) => [x, y];
  assert.equal(canvas.arePointsLocked(), true);
  canvas.pointMapper = null;
  canvas.pointsVisible = false;
  assert.equal(canvas.arePointsLocked(), true);
});

test("locked points cannot be dragged or added", () => {
  const canvas = makeCanvas();
  canvas.pointMapper = (x, y) => [x, y];
  canvas.onMouseDown(mouse(10, 20));
  assert.equal(canvas.isDragging, false);
  canvas.onDblClick(mouse(50, 50));
  assert.equal(canvas.calibrationPoints.length, 2);
});

test("unlocked points can be dragged and added", () => {
  const canvas = makeCanvas();
  canvas.onMouseDown(mouse(10, 20));
  assert.equal(canvas.isDragging, true);
  canvas.onMouseUp(mouse(10, 20));
  canvas.onDblClick(mouse(50, 50));
  assert.equal(canvas.calibrationPoints.length, 3);
});

test("setting a mapper redraws only a fully loaded frame", () => {
  const canvas = makeCanvas();
  canvas.drawImage = spy();
  canvas.updateImageSrc("data:image/jpeg;base64,next");
  canvas.setPointMapper((x, y) => [x, y], true);
  assert.equal(canvas.drawImage.calls.length, 0, "frame still decoding");

  canvas.image.complete = true;
  canvas.image.naturalWidth = 100;
  canvas.setPointMapper(null, false);
  assert.equal(canvas.drawImage.calls.length, 1);
  assert.equal(canvas.pointMapper, null);
  assert.equal(canvas.pointsVisible, false);
});
