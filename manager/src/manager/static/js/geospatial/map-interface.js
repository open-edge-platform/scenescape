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
  static SNAPSHOT_SIZE_PX = 1280;

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

  _mercatorWorldSize(zoom) {
    return 256 * Math.pow(2, zoom);
  }

  _lngToMercatorX(lng, zoom) {
    return ((lng + 180) / 360) * this._mercatorWorldSize(zoom);
  }

  _latToMercatorY(lat, zoom) {
    const clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
    const s = Math.sin((clamped * Math.PI) / 180);
    const y = 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
    return y * this._mercatorWorldSize(zoom);
  }

  _mercatorXToLng(x, zoom) {
    return (x / this._mercatorWorldSize(zoom)) * 360 - 180;
  }

  _mercatorYToLat(y, zoom) {
    const n = Math.PI - (2 * Math.PI * y) / this._mercatorWorldSize(zoom);
    return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  }

  /**
   * WGS84 corners of the 1280×1280 snapshot (not the UI map widget).
   * Order: SW, SE, NE, NW — CCW from image lower-left, matching local XYZ.
   */
  snapshotCornersLla(lat, lng, zoom, bearing = 0, altitude = 0) {
    const size = this.constructor.SNAPSHOT_SIZE_PX;
    const half = size / 2;
    const cx = this._lngToMercatorX(lng, zoom);
    const cy = this._latToMercatorY(lat, zoom);
    const theta = ((Number(bearing) || 0) * Math.PI) / 180;
    const cos = Math.cos(theta);
    const sin = Math.sin(theta);
    // Image offsets from center: x right, y down (SW, SE, NE, NW of the image).
    const imageCorners = [
      [-half, half],
      [half, half],
      [half, -half],
      [-half, -half],
    ];
    return imageCorners.map(([dx, dy]) => {
      const eastPx = dx * cos + dy * -sin;
      const southPx = dx * sin + dy * cos;
      return [
        this._mercatorYToLat(cy + southPx, zoom),
        this._mercatorXToLng(cx + eastPx, zoom),
        altitude,
      ];
    });
  }

  snapshotQuadrantCenters(lat, lng, zoom, bearing = 0) {
    const size = this.constructor.SNAPSHOT_SIZE_PX;
    const quarter = size / 4;
    const cx = this._lngToMercatorX(lng, zoom);
    const cy = this._latToMercatorY(lat, zoom);
    const theta = ((Number(bearing) || 0) * Math.PI) / 180;
    const cos = Math.cos(theta);
    const sin = Math.sin(theta);
    const toLatLng = (dx, dy) => {
      const eastPx = dx * cos + dy * -sin;
      const southPx = dx * sin + dy * cos;
      return {
        lat: this._mercatorYToLat(cy + southPx, zoom),
        lng: this._mercatorXToLng(cx + eastPx, zoom),
      };
    };
    return {
      NW: { ...toLatLng(-quarter, -quarter), x: 0, y: 0 },
      NE: { ...toLatLng(quarter, -quarter), x: 640, y: 0 },
      SW: { ...toLatLng(-quarter, quarter), x: 0, y: 640 },
      SE: { ...toLatLng(quarter, quarter), x: 640, y: 640 },
    };
  }

  writeGeospatialFormFields(lat, lng, zoom, bearing = 0) {
    const scale = this.calculateScale(lat, zoom);
    const scaleField = document.getElementById("id_scale");
    if (scaleField) {
      scaleField.value = scale.toFixed(2);
    }
    const mapCornersField = document.getElementById("id_map_corners_lla");
    if (mapCornersField) {
      mapCornersField.value = JSON.stringify(
        this.snapshotCornersLla(lat, lng, zoom, bearing, 0),
      );
    }
    const outputLlaField = document.getElementById("id_output_lla");
    if (outputLlaField) {
      outputLlaField.value = "True";
    }
    return scale;
  }

  getCsrfToken() {
    const input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) {
      return input.value;
    }
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  dispatchSnapshotResult(detail) {
    window.dispatchEvent(
      new CustomEvent("ss-geospatial-snapshot", { detail: detail || {} }),
    );
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
