// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";

const source = await readFile(
  new URL("../../../manager/src/manager/static/js/utils.js", import.meta.url),
  "utf8",
);

const SCALE = 100;
const Y_MAX = 600;

// Fresh module instance per test so mapOrigin state never leaks between tests.
async function loadUtils() {
  const context = vm.createContext({ console, scene_precision: 3 });
  const module = new vm.SourceTextModule(source, { context });
  await module.link(async () => {
    const exports = {
      FX: 0,
      FY: 1,
      CX: 2,
      CY: 3,
      REST_URL: "",
      POINT_CORRESPONDENCE: "",
      EULER: "",
    };
    return new vm.SyntheticModule(
      Object.keys(exports),
      function () {
        for (const [name, value] of Object.entries(exports))
          this.setExport(name, value);
      },
      { context },
    );
  });
  await module.evaluate();
  const utils = module.namespace;
  // Copy vm-realm arrays into this realm so deepStrictEqual prototypes match.
  return {
    setMapOrigin: utils.setMapOrigin,
    pixelsToMeters: (...args) => [...utils.pixelsToMeters(...args)],
    metersToPixels: (...args) => [...utils.metersToPixels(...args)],
  };
}

function assertClose(actual, expected) {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, i) =>
    assert.ok(
      Math.abs(value - expected[i]) < 1e-9,
      `index ${i}: ${value} !== ${expected[i]}`,
    ),
  );
}

test("default origin is [0, 0]", async () => {
  const { pixelsToMeters, metersToPixels } = await loadUtils();
  assertClose(pixelsToMeters([0, Y_MAX], SCALE, Y_MAX), [0, 0]);
  assertClose(pixelsToMeters([50, 100], SCALE, Y_MAX), [0.5, 5]);
  assert.deepEqual(metersToPixels([0.5, 5], SCALE, Y_MAX), [50, 100]);
});

test("non-zero origin offsets both axes", async () => {
  const { setMapOrigin, pixelsToMeters, metersToPixels } = await loadUtils();
  setMapOrigin([10, -5]);

  // Bottom-left pixel of the map maps to the origin itself.
  assertClose(pixelsToMeters([0, Y_MAX], SCALE, Y_MAX), [10, -5]);
  // Top-left pixel is Y_MAX / SCALE meters above the origin.
  assertClose(pixelsToMeters([0, 0], SCALE, Y_MAX), [10, 1]);
  assertClose(pixelsToMeters([200, 100], SCALE, Y_MAX), [12, 0]);

  assert.deepEqual(metersToPixels([10, -5], SCALE, Y_MAX), [0, Y_MAX]);
  assert.deepEqual(metersToPixels([12, 0], SCALE, Y_MAX), [200, 100]);
  assert.deepEqual(metersToPixels([10, 1], SCALE, Y_MAX), [0, 0]);
});

test("px -> m -> px round trip preserves pixels with y-flip", async () => {
  const { setMapOrigin, pixelsToMeters, metersToPixels } = await loadUtils();
  setMapOrigin([-3.25, 7.5]);

  for (const pixels of [
    [0, 0],
    [0, Y_MAX],
    [123, 456],
    [799, 1],
    [400, 300],
  ]) {
    const meters = pixelsToMeters(pixels, SCALE, Y_MAX);
    assert.deepEqual(metersToPixels(meters, SCALE, Y_MAX), pixels);
  }

  // Larger pixel y is lower on screen, so it must map to smaller world y.
  const upper = pixelsToMeters([0, 100], SCALE, Y_MAX);
  const lower = pixelsToMeters([0, 500], SCALE, Y_MAX);
  assert.ok(upper[1] > lower[1]);
});

test("z passes through unchanged", async () => {
  const { setMapOrigin, pixelsToMeters, metersToPixels } = await loadUtils();
  setMapOrigin([10, -5]);
  assert.equal(pixelsToMeters([0, Y_MAX, 1.5], SCALE, Y_MAX)[2], "1.500");
  assert.equal(metersToPixels([10, -5, 1.5], SCALE, Y_MAX)[2], 1.5);
});

test("NaN / missing origin components fall back to 0", async () => {
  const { setMapOrigin, pixelsToMeters, metersToPixels } = await loadUtils();

  // What sscape.js passes when the origin inputs are empty.
  setMapOrigin([parseFloat(""), parseFloat(undefined)]);
  assertClose(pixelsToMeters([50, 100], SCALE, Y_MAX), [0.5, 5]);
  assert.deepEqual(metersToPixels([0.5, 5], SCALE, Y_MAX), [50, 100]);

  setMapOrigin([undefined, Infinity]);
  assertClose(pixelsToMeters([0, Y_MAX], SCALE, Y_MAX), [0, 0]);

  // Only the invalid component falls back; a valid one is kept.
  setMapOrigin([4, NaN]);
  assertClose(pixelsToMeters([0, Y_MAX], SCALE, Y_MAX), [4, 0]);

  // A previously set origin is replaced, not retained, by a NaN origin.
  setMapOrigin([10, -5]);
  setMapOrigin([NaN, NaN]);
  assertClose(pixelsToMeters([0, Y_MAX], SCALE, Y_MAX), [0, 0]);
});
