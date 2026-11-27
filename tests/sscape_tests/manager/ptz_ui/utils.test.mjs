// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

const { metersToPixels, pixelsToMeters, setMapOrigin } =
  await import("/static/js/utils.js");

const SCALE = 10;
const HEIGHT = 200;

afterEach(() => setMapOrigin([0, 0]));

test("without an origin the image corner is local (0, 0)", () => {
  assert.deepEqual(metersToPixels([5, 2], SCALE, HEIGHT), [50, 180]);
  assert.deepEqual(pixelsToMeters([50, 180], SCALE, HEIGHT), [5, 2]);
});

test("the origin shifts local meters relative to the image corner", () => {
  setMapOrigin([45, 38.5]);
  assert.deepEqual(metersToPixels([45, 38.5], SCALE, HEIGHT), [0, 200]);
  assert.deepEqual(metersToPixels([50, 40.5], SCALE, HEIGHT), [50, 180]);
  assert.deepEqual(pixelsToMeters([0, 200], SCALE, HEIGHT), [45, 38.5]);
});

test("meters to pixels and back round-trips with an origin", () => {
  setMapOrigin([-12.5, 7]);
  const meters = [3.5, 20.1];
  const back = pixelsToMeters(
    metersToPixels(meters, SCALE, HEIGHT),
    SCALE,
    HEIGHT,
  );
  assert.ok(Math.abs(back[0] - meters[0]) <= 0.5 / SCALE);
  assert.ok(Math.abs(back[1] - meters[1]) <= 0.5 / SCALE);
});

test("an origin change applies to later conversions only", () => {
  const before = metersToPixels([10, 10], SCALE, HEIGHT);
  setMapOrigin([10, 10]);
  assert.deepEqual(metersToPixels([10, 10], SCALE, HEIGHT), [0, 200]);
  assert.notDeepEqual(before, [0, 200]);
});
