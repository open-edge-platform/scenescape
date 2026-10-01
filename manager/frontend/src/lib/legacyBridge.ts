// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Typed React → hybrid bridges.
 *
 * Under `ssUseReactMap`, fit / number helpers use only `window.ssMap`
 * (installed by React). Snap `window.fitSceneMapDisplay` / `numberRois`
 * fallbacks run only for non-React map pages (calibrate / Snap-map scenes).
 *
 * Occupancy color helpers still call into `sscape.js` (sectors apply to
 * React polygons). Geometry persist uses React-installed `ssPersistGeometry`.
 */

type PersistOptions = { preferHidden?: boolean } | string[];

type RoiColorSectors = {
  thresholds: { color: string; color_min: number }[];
  range_max: number;
};

function useReactMap(): boolean {
  return Boolean(window.ssUseReactMap);
}

export function fitSceneMapDisplay(): void {
  if (typeof window.ssMap?.fit === "function") {
    window.ssMap.fit();
    return;
  }
  if (!useReactMap()) {
    window.fitSceneMapDisplay?.();
  }
}

export function numberRois(): void {
  if (typeof window.ssMap?.numberRois === "function") {
    window.ssMap.numberRois();
    return;
  }
  if (!useReactMap()) {
    window.numberRois?.();
  }
}

export function numberTripwires(): void {
  if (typeof window.ssMap?.numberTripwires === "function") {
    window.ssMap.numberTripwires();
    return;
  }
  if (!useReactMap()) {
    window.numberTripwires?.();
  }
}

export function syncRoiColorSectors(
  uuid: string,
  sectors: RoiColorSectors,
): void {
  window.ssSyncRoiColorSectors?.(uuid, sectors);
}

export function reapplyRoiColors(): void {
  window.ssReapplyRoiColors?.();
}

export function persistGeometry(
  options?: PersistOptions,
): void | Promise<void> {
  return window.ssPersistGeometry?.(options);
}

declare global {
  interface Window {
    ssUseReactMap?: boolean;
    ssInitSceneMap?: (attempt?: number) => boolean;
    ssSyncRoiColorSectors?: (uuid: string, sectors: RoiColorSectors) => void;
    ssReapplyRoiColors?: () => void;
  }
}
