// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Match sscape.js meter ↔ pixel conventions. */

export function pixelsToMeters(
  px: number,
  py: number,
  scale: number,
  sceneYMax: number,
): [number, number] {
  return [px / scale, (sceneYMax - py) / scale];
}

export function metersToPixels(
  mx: number,
  my: number,
  scale: number,
  sceneYMax: number,
): [number, number] {
  return [mx * scale, sceneYMax - my * scale];
}

export function readMapScale(): number {
  const el = document.getElementById("scale") as HTMLInputElement | null;
  const n = Number(el?.value || el?.textContent || "100");
  return Number.isFinite(n) && n > 0 ? n : 100;
}

export function readSceneYMax(fallback = 1000): number {
  const img = document.querySelector("#svgout image, #map img") as
    SVGImageElement | HTMLImageElement | null;
  if (img && "height" in img && typeof img.height === "object") {
    const h = Number((img as SVGImageElement).getAttribute("height"));
    if (Number.isFinite(h) && h > 0) {
      return h;
    }
  }
  if (img && "naturalHeight" in img && img.naturalHeight > 0) {
    return img.naturalHeight;
  }
  return fallback;
}
