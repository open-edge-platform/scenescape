// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Map Interface - Strategy Pattern Base
class MapInterface {
  constructor() {
    if (new.target === MapInterface) {
      throw new TypeError("Cannot instantiate abstract class MapInterface");
    }
  }

  // Abstract methods that must be implemented by concrete strategies
  async initialize(containerId, config) {
    throw new Error("Method 'initialize' must be implemented");
  }

  moveToLocation(input) {
    throw new Error("Method 'moveToLocation' must be implemented");
  }

  generateBounds() {
    throw new Error("Method 'generateBounds' must be implemented");
  }

  generateSnapshot() {
    throw new Error("Method 'generateSnapshot' must be implemented");
  }

  prepareScreenshot() {
    throw new Error("Method 'prepareScreenshot' must be implemented");
  }

  restoreControls() {
    throw new Error("Method 'restoreControls' must be implemented");
  }

  getBounds() {
    throw new Error("Method 'getBounds' must be implemented");
  }

  getCenter() {
    throw new Error("Method 'getCenter' must be implemented");
  }

  getZoom() {
    throw new Error("Method 'getZoom' must be implemented");
  }

  // Common utility methods
  calculateScale(lat, zoom) {
    // Earth's circumference at equator in meters
    const EARTH_CIRCUMFERENCE = 40075016.686;

    // At zoom level 0, the entire world (360 degrees) fits in 256 pixels
    const pixelsPerDegree = (256 * Math.pow(2, zoom)) / 360;

    // Convert longitude degrees to meters at the given latitude
    const metersPerDegreeLng =
      (EARTH_CIRCUMFERENCE / 360) * Math.cos((lat * Math.PI) / 180);

    // Calculate pixels per meter
    const pixelsPerMeter = pixelsPerDegree / metersPerDegreeLng;

    return pixelsPerMeter;
  }

  parseCoordinates(input) {
    const coordMatch = input.match(/^(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)$/);
    if (coordMatch) {
      return {
        lat: parseFloat(coordMatch[1]),
        lng: parseFloat(coordMatch[2]),
      };
    }
    return null;
  }

  showApiKeyModal(config) {
    // Validate required configuration
    const requiredFields = ["providerName", "envVarName", "signupUrl"];
    for (const field of requiredFields) {
      if (!config[field]) {
        console.error(`Missing required field '${field}' in modal config`);
        return;
      }
    }

    const { providerName, envVarName, signupUrl } = config;

    // Simple alert-based implementation - no z-index issues!
    const message =
      `${providerName} API Key Required\n\n` +
      `To use ${providerName} geospatial maps, you need to set the ${envVarName} environment variable.\n\n` +
      `You can get an API key from: ${signupUrl}`;

    alert(message);

    // Also log to console for developer reference
    console.error(`${providerName} API Key Missing:`, {
      envVarName,
      signupUrl,
      message: `Please set the ${envVarName} environment variable`,
    });
  }
}
