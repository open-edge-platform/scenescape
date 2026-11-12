// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* Test harness for pure JS helpers from glb-alignment.js */

"use strict";

const vm = require("vm");
const fs = require("fs");
const path = require("path");

const jsDir = path.join(
  __dirname,
  "../../../manager/src/manager/static/js/geospatial",
);

// Load geo-overlay-math.js for GeoOverlayMath
const geoOverlayCode = fs.readFileSync(
  path.join(jsDir, "geo-overlay-math.js"),
  "utf8",
);

// Load glb-alignment.js
const glbAlignCode = fs.readFileSync(
  path.join(jsDir, "glb-alignment.js"),
  "utf8",
);

// Create context with required globals
const context = vm.createContext({
  module: { exports: {} },
  console,
  Math,
  Object,
  Array,
  String,
  Number,
  Boolean,
  isFinite,
});

// Execute both modules in the context
vm.runInContext(geoOverlayCode, context);
vm.runInContext(glbAlignCode, context);

// Extract exports
const glbExports = context.module.exports;

const NON_FINITE = { NaN: NaN, Infinity: Infinity, "-Infinity": -Infinity };
const input = JSON.parse(require("fs").readFileSync(0, "utf-8"), (_, v) =>
  typeof v === "string" && Object.hasOwn(NON_FINITE, v) ? NON_FINITE[v] : v,
);
const testName = input.test;
const args = input.args;

let result = null;

try {
  switch (testName) {
    case "clampHeading":
      result = glbExports.clampHeading(args.value);
      break;
    case "dragAnchor":
      result = glbExports.dragAnchor(args.anchor, args.grab, args.cur);
      break;
    case "buildOverlayCorners":
      result = glbExports.buildOverlayCorners(args.anchor, args.footprint);
      break;
    default:
      throw new Error(`Unknown test: ${testName}`);
  }
  console.log(JSON.stringify({ ok: true, result }));
} catch (err) {
  console.log(JSON.stringify({ ok: false, error: err.message }));
  process.exit(1);
}
