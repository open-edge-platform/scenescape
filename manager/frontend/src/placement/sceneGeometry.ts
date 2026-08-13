// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { IDENTITY_POSE, type SceneEulerPose } from "./placementTypes";

/** Map / mesh metadata used to decide whether 3D placement can run. */
export type SceneGeometrySpec = {
  id: string;
  name: string;
  mapUrl: string | null;
  scale: number | null;
  isGlb: boolean;
  /** Scene mesh pose (Y-up GLB → first-quadrant Z-up). Identity for 2D maps. */
  meshPose: SceneEulerPose;
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

function asFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function asVec3(
  primary: unknown,
  fallbacks: [unknown, unknown, unknown],
  defaults: [number, number, number],
): [number, number, number] {
  const fromArray = Array.isArray(primary)
    ? [
        asFiniteNumber(primary[0]),
        asFiniteNumber(primary[1]),
        asFiniteNumber(primary[2]),
      ]
    : [null, null, null];
  return [
    fromArray[0] ?? asFiniteNumber(fallbacks[0]) ?? defaults[0],
    fromArray[1] ?? asFiniteNumber(fallbacks[1]) ?? defaults[1],
    fromArray[2] ?? asFiniteNumber(fallbacks[2]) ?? defaults[2],
  ];
}

/** Mesh TRS that orients a GLB into scene-local meters (same as the 3D viewer). */
export function meshPoseFromRest(
  payload: Record<string, unknown>,
): SceneEulerPose {
  return {
    translation: asVec3(
      payload.mesh_translation,
      [payload.translation_x, payload.translation_y, payload.translation_z],
      IDENTITY_POSE.translation,
    ),
    rotation: asVec3(
      payload.mesh_rotation,
      [payload.rotation_x, payload.rotation_y, payload.rotation_z],
      IDENTITY_POSE.rotation,
    ),
    scale: asVec3(
      payload.mesh_scale,
      [payload.scale_x, payload.scale_y, payload.scale_z],
      IDENTITY_POSE.scale,
    ),
  };
}

export function sceneGeometryFromRest(
  payload: Record<string, unknown>,
): SceneGeometrySpec {
  const mapUrl = asUrl(payload.map) || asUrl(payload.mapUrl);
  const isGlb = isGlbUrl(mapUrl);
  return {
    id: String(payload.uid || payload.id || ""),
    name: String(payload.name || ""),
    mapUrl,
    scale: asPositiveNumber(payload.scale),
    isGlb,
    meshPose: isGlb ? meshPoseFromRest(payload) : { ...IDENTITY_POSE },
  };
}

export function sceneHasPlaceableGeometry(spec: SceneGeometrySpec): boolean {
  return Boolean(spec.mapUrl);
}
