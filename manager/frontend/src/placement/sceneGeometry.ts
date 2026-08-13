// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Map / mesh metadata used to decide whether 3D placement can run. */
export type SceneGeometrySpec = {
  id: string;
  name: string;
  mapUrl: string | null;
  scale: number | null;
  isGlb: boolean;
};

function asUrl(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function asPositiveNumber(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0) {
    return null;
  }
  return n;
}

export function isGlbUrl(url: string | null): boolean {
  if (!url) {
    return false;
  }
  const path = url.split("?")[0].toLowerCase();
  return path.endsWith(".glb") || path.endsWith(".gltf");
}

export function sceneGeometryFromRest(
  payload: Record<string, unknown>,
): SceneGeometrySpec {
  const mapUrl = asUrl(payload.map) || asUrl(payload.mapUrl);
  return {
    id: String(payload.uid || payload.id || ""),
    name: String(payload.name || ""),
    mapUrl,
    scale: asPositiveNumber(payload.scale),
    isGlb: isGlbUrl(mapUrl),
  };
}

export function sceneHasPlaceableGeometry(spec: SceneGeometrySpec): boolean {
  return Boolean(spec.mapUrl);
}
