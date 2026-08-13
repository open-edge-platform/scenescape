// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Must match MapInterface.SNAPSHOT_SIZE_PX and the static snapshot request. */
export const SNAPSHOT_SIZE_PX = 1280;

export type LlaCorner = [number, number, number];

export function scaleFromView(lat: number, zoom: number): number {
  const earth = 40075016.686;
  const pixelsPerDegree = (256 * Math.pow(2, zoom)) / 360;
  const metersPerDegreeLng =
    (earth / 360) * Math.cos((lat * Math.PI) / 180);
  return pixelsPerDegree / metersPerDegreeLng;
}

function worldSize(zoom: number): number {
  return 256 * Math.pow(2, zoom);
}

function lngToMercatorX(lng: number, zoom: number): number {
  return ((lng + 180) / 360) * worldSize(zoom);
}

function latToMercatorY(lat: number, zoom: number): number {
  const clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
  const s = Math.sin((clamped * Math.PI) / 180);
  const y = 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
  return y * worldSize(zoom);
}

function mercatorXToLng(x: number, zoom: number): number {
  return (x / worldSize(zoom)) * 360 - 180;
}

function mercatorYToLat(y: number, zoom: number): number {
  const n = Math.PI - (2 * Math.PI * y) / worldSize(zoom);
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

/**
 * WGS84 corners of the 1280×1280 snapshot (not the UI map widget).
 * Order: SW, SE, NE, NW — CCW from image lower-left, matching local XYZ.
 */
export function snapshotCornersLla(
  lat: number,
  lng: number,
  zoom: number,
  bearing = 0,
  altitude = 0,
): LlaCorner[] {
  const half = SNAPSHOT_SIZE_PX / 2;
  const cx = lngToMercatorX(lng, zoom);
  const cy = latToMercatorY(lat, zoom);
  const theta = ((Number(bearing) || 0) * Math.PI) / 180;
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const imageCorners: Array<[number, number]> = [
    [-half, half],
    [half, half],
    [half, -half],
    [-half, -half],
  ];
  return imageCorners.map(([dx, dy]) => {
    const eastPx = dx * cos + dy * -sin;
    const southPx = dx * sin + dy * cos;
    return [
      mercatorYToLat(cy + southPx, zoom),
      mercatorXToLng(cx + eastPx, zoom),
      altitude,
    ];
  });
}

export function snapshotCornersJson(
  lat: number,
  lng: number,
  zoom: number,
  bearing = 0,
): string {
  return JSON.stringify(snapshotCornersLla(lat, lng, zoom, bearing, 0));
}
