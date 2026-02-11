// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import {
  FX,
  FY,
  CX,
  CY,
  K1,
  K2,
  P1,
  P2,
  K3,
  REST_URL,
  POINT_CORRESPONDENCE,
  EULER,
} from "/static/js/constants.js";

// Convert a point from pixels to meters
function pixelsToMeters(pixels, scale, scene_y_max) {
  var meters = [];

  // Scale-only in x
  meters[0] = parseFloat(pixels[0] / scale);

  // Move y axis to bottom and also scale
  meters[1] = parseFloat((scene_y_max - pixels[1]) / scale);

  if (pixels.length == 3) {
    // Leave z alone
    meters[2] = pixels[2].toFixed(scene_precision);
  }

  return meters;
}

// Convert a point from meters to pixels
function metersToPixels(meters, scale, scene_y_max) {
  var pixels = [];

  // Scale-only in x
  pixels[0] = Math.round(meters[0] * scale);

  // Move y axis to top and also scale
  pixels[1] = Math.round(scene_y_max - meters[1] * scale);

  // z, if provided, remains unchanged since it should be in meters already
  if (meters.length == 3) {
    pixels[2] = meters[2];
  }

  return pixels;
}

function compareIntrinsics(
  intrinsics,
  msgIntrinsics,
  distortion,
  msgDistortion,
) {
  if (
    intrinsics["fx"] === msgIntrinsics[FX] &&
    intrinsics["fy"] === msgIntrinsics[FY] &&
    intrinsics["cx"] === msgIntrinsics[CX] &&
    intrinsics["cy"] === msgIntrinsics[CY] &&
    distortion["k1"] === msgDistortion[K1] &&
    distortion["k2"] === msgDistortion[K2] &&
    distortion["p1"] === msgDistortion[P1] &&
    distortion["p2"] === msgDistortion[P2] &&
    distortion["k3"] === msgDistortion[K3]
  ) {
    return true;
  }
  return false;
}

const waitUntil = (condition, checkInterval, maxWaitTime) => {
  return new Promise((resolve, reject) => {
    let interval = setInterval(() => {
      if (condition()) {
        clearInterval(interval);
        clearTimeout(timeout);
        resolve();
      }
    }, checkInterval);

    let timeout = setTimeout(() => {
      clearInterval(interval);
      reject(new Error("Timeout exceeded"));
    }, maxWaitTime);
  });
};

function initializeOpencv() {
  return new Promise((resolve) => {
    if (cv.getBuildInformation?.() !== undefined) {
      // Already loaded
      resolve(true);
    } else {
      cv.onRuntimeInitialized = () => {
        resolve(true);
      };
    }
  });
}

// Responsive canvas implementation (handle browser window resizing)
// https://threejs.org/manual/#en/responsive
function resizeRendererToDisplaySize(renderer) {
  const canvas = renderer.domElement;
  const pixelRatio = window.devicePixelRatio;
  const width = (canvas.clientWidth * pixelRatio) | 0;
  const height = (canvas.clientHeight * pixelRatio) | 0;
  const needResize = canvas.width !== width || canvas.height !== height;

  if (needResize) {
    renderer.setSize(width, height, false);
  }

  return needResize;
}

function checkMqttConnection(url) {
  return new Promise((resolve, reject) => {
    try {
      console.log(`Testing MQTT WebSocket connection to: ${url}`);
      const client = mqtt.connect(url);

      client.on("connect", () => {
        console.log(`Successfully connected to ${url}`);
        client.end(); // Close the connection after testing
        resolve(url);
      });

      client.on("error", (error) => {
        console.error(`Connection failed to ${url}:`, error);
        client.end(); // Ensure the client is closed on error
        reject(null);
      });

      client.on("close", () => {
        console.warn(`Connection to ${url} closed.`);
      });
    } catch (err) {
      console.error(
        `Error during MQTT WebSocket connection test for ${url}:`,
        err,
      );
      reject(null);
    }
  });
}

function updateElements(elements, action, condition) {
  elements.forEach(function (e) {
    const element = document.getElementById(e);
    if (element) {
      element[action] = condition;
    }
  });
}

export {
  pixelsToMeters,
  metersToPixels,
  compareIntrinsics,
  waitUntil,
  initializeOpencv,
  resizeRendererToDisplaySize,
  checkMqttConnection,
  updateElements,
};
