// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* global module */

"use strict";

// WGS-84 ellipsoid parameters
const EQUATORIAL_RADIUS = 6378137.0;
const POLAR_RADIUS = 6356752.314245;

/**
 * Wrap an angle in degrees into [-180, 180).
 * @param {number} deg - Angle in degrees
 * @returns {number} Wrapped angle in degrees
 */
function _wrapDegrees180(deg) {
  return ((deg + 180.0) % 360.0) - 180.0;
}

/**
 * Compute WGS-84 meridional radius (M), prime-vertical radius (N), and cos(lat).
 * @param {number} latRad - Latitude in radians
 * @returns {Object} { M, N, cosLat } in metres and unitless
 */
function _localTangentRadii(latRad) {
  const eSq =
    1.0 -
    (POLAR_RADIUS * POLAR_RADIUS) / (EQUATORIAL_RADIUS * EQUATORIAL_RADIUS);
  const sinLatSq = Math.sin(latRad) * Math.sin(latRad);
  const denom = Math.sqrt(1.0 - eSq * sinLatSq);
  const M = (EQUATORIAL_RADIUS * (1.0 - eSq)) / (denom * denom * denom);
  const N = EQUATORIAL_RADIUS / denom;
  const cosLat = Math.cos(latRad);
  return { M, N, cosLat };
}

/**
 * Compute LLA corners of a rectangular footprint from centre, heading, and dimensions.
 * Local footprint corners are at SW (-W/2,-H/2), SE (+W/2,-H/2), NE (+W/2,+H/2), NW (-W/2,+H/2).
 * Heading is in degrees, where 0° means local +Y points true north. Clockwise rotation.
 * Uses WGS-84 local-tangent approximation.
 *
 * @param {number} lat - Centre latitude in degrees
 * @param {number} lng - Centre longitude in degrees
 * @param {number} headingDeg - Heading in degrees (0 = north, 90 = east)
 * @param {number} widthM - Footprint width in metres (W, east-west extent)
 * @param {number} heightM - Footprint height in metres (H, north-south extent)
 * @returns {Array} Corners as [{lat, lng}, ...] for SW, SE, NE, NW
 * @throws {RangeError} If inputs are invalid
 */
function footprintCornersLLA(lat, lng, headingDeg, widthM, heightM) {
  // Input validation
  if (
    !isFinite(lat) ||
    !isFinite(lng) ||
    !isFinite(headingDeg) ||
    !isFinite(widthM) ||
    !isFinite(heightM)
  ) {
    throw new RangeError("All numeric inputs must be finite (not NaN or inf)");
  }
  if (Math.abs(lat) > 90.0) {
    throw new RangeError(`Latitude must be in [-90, 90], got ${lat}`);
  }
  if (Math.abs(lng) > 180.0) {
    throw new RangeError(`Longitude must be in [-180, 180], got ${lng}`);
  }
  if (widthM <= 0.0) {
    throw new RangeError(`Width must be positive, got ${widthM}`);
  }
  if (heightM <= 0.0) {
    throw new RangeError(`Height must be positive, got ${heightM}`);
  }

  // Convert heading to radians and compute rotation
  const psiRad = (headingDeg * Math.PI) / 180.0;
  const cosPsi = Math.cos(psiRad);
  const sinPsi = Math.sin(psiRad);

  // Local offsets for each corner: (x, y) in footprint-local coords
  const cornersLocal = [
    [-widthM / 2.0, -heightM / 2.0], // SW
    [widthM / 2.0, -heightM / 2.0], // SE
    [widthM / 2.0, heightM / 2.0], // NE
    [-widthM / 2.0, heightM / 2.0], // NW
  ];

  // Convert centre to radians
  const latRad = (lat * Math.PI) / 180.0;
  const lngRad = (lng * Math.PI) / 180.0;
  const { M, N, cosLat } = _localTangentRadii(latRad);

  const cornersLLA = [];
  for (let i = 0; i < cornersLocal.length; i++) {
    const [xLocal, yLocal] = cornersLocal[i];

    // Rotate local (x, y) by heading to get (east, north) in metres
    const east = xLocal * cosPsi + yLocal * sinPsi;
    const north = -xLocal * sinPsi + yLocal * cosPsi;

    // Convert metres to radians using local tangent plane
    const dlatRad = north / M;
    const dlngRad = east / (N * cosLat);

    // Add to centre
    const latCorner = latRad + dlatRad;
    const lngCorner = lngRad + dlngRad;

    // Convert back to degrees; normalise longitude to [-180, 180)
    const latDeg = (latCorner * 180.0) / Math.PI;
    const lngDeg = _wrapDegrees180((lngCorner * 180.0) / Math.PI);

    cornersLLA.push({ lat: latDeg, lng: lngDeg });
  }

  return cornersLLA;
}

/**
 * Compute CSS transform matrix and dimensions for a geospatial overlay image.
 * Given pixel positions of three corners of the image (NW, NE, SW), compute the
 * CSS transform matrix that maps the image's local coordinates to screen coordinates.
 *
 * @param {Object} nw - NW corner as {x, y} (top-left, in pixels)
 * @param {Object} ne - NE corner as {x, y} (top-right, in pixels)
 * @param {Object} sw - SW corner as {x, y} (bottom-left, in pixels)
 * @returns {Object} { width, height, matrix: [a, b, c, d, e, f] }
 *   where width and height are the image dimensions in pixels,
 *   and matrix is suitable for CSS transform: matrix(a,b,c,d,e,f)
 *   with transform-origin: 0 0
 */
function overlayCssMatrix(nw, ne, sw) {
  // Compute image dimensions from screen corner positions
  const width = Math.hypot(ne.x - nw.x, ne.y - nw.y);
  const height = Math.hypot(sw.x - nw.x, sw.y - nw.y);

  // Guard against zero dimensions
  if (width === 0 || height === 0) {
    return {
      width: width,
      height: height,
      matrix: [1, 0, 0, 1, nw.x, nw.y],
    };
  }

  const a = (ne.x - nw.x) / width;
  const b = (ne.y - nw.y) / width;
  const c = (sw.x - nw.x) / height;
  const d = (sw.y - nw.y) / height;
  const e = nw.x;
  const f = nw.y;

  return {
    width: width,
    height: height,
    matrix: [a, b, c, d, e, f],
  };
}

// Export for both browsers and Node.js
const GeoOverlayMath = { footprintCornersLLA, overlayCssMatrix };
if (typeof module !== "undefined" && module.exports) {
  module.exports = GeoOverlayMath;
}
