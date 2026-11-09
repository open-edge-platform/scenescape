// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Module-loader hooks that let scenecamera.js be imported outside the browser:
 * the real constants.js is served from disk and every other "/static/..." import
 * (THREE, toast, controls, ...) is replaced by a minimal stub.
 */
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const STATIC_JS = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../../manager/src/manager/static/js",
);

const STUB_URL = "stub:generic";
const THREE_URL = "stub:three";

const STUB_SOURCE = `
  export default class {}
  export const compareIntrinsics = () => {};
  export const startCameraCalibration = () => {};
  export const normalizeDistortion = () => {};
  export const PTZ_AWAY_MESSAGE = "";
  export const PTZ_HOME_ANGLE_TOLERANCE_RAD = 0;
  export class PTZFrameGate {}
  export class PTZPoseExpiry {}
  export const expiredPTZPoseContext = () => {};
  export const isPTZMoving = () => {};
  export const isPTZPositionUnknown = () => {};
  export const ptzMatricesClose = () => {};
  export const ptzPoseToCameraMatrix = () => {};
`;

const THREE_SOURCE = `
  export const MathUtils = {
    degToRad: (d) => (d * Math.PI) / 180,
    radToDeg: (r) => (r * 180) / Math.PI,
  };
  export class Object3D {}
`;

export async function resolve(specifier, context, nextResolve) {
  if (specifier === "/static/js/constants.js") {
    return {
      url: pathToFileURL(join(STATIC_JS, "constants.js")).href,
      shortCircuit: true,
    };
  }
  if (specifier === "/static/assets/three.module.js") {
    return { url: THREE_URL, shortCircuit: true };
  }
  if (specifier.startsWith("/static/")) {
    return { url: STUB_URL, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (url === STUB_URL || url === THREE_URL) {
    return {
      format: "module",
      source: url === THREE_URL ? THREE_SOURCE : STUB_SOURCE,
      shortCircuit: true,
    };
  }
  // Browser sources are ES modules but have no package "type"; Node < 22 would treat them as CommonJS.
  if (url.startsWith(pathToFileURL(STATIC_JS).href) && url.endsWith(".js")) {
    return nextLoad(url, { ...context, format: "module" });
  }
  return nextLoad(url, context);
}
