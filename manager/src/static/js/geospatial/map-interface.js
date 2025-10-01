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
  calculateScale(lat, zoom, imageWidth) {
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

  displayBoundsOutput(corners, scale, zoom) {
    let output = "<b>LLA Coordinates of Map Corners:</b><br><ul>";
    corners.forEach((c) => {
      output += `<li>${c.name}: (${c.lat.toFixed(6)}, ${c.lng.toFixed(6)}, ${c.alt})</li>`;
    });
    output += "</ul>";
    output += `<b>Scale:</b> ${scale.toFixed(2)} pixels/meter<br>`;
    output += `<b>Resolution:</b> ${(1 / scale).toFixed(2)} meters/pixel<br>`;
    output += `<b>Zoom Level:</b> ${zoom.toFixed(1)}<br>`;
    document.getElementById("boundsOutput").innerHTML = output;
  }
}
