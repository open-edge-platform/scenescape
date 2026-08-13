// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type PlacementGizmoMode = "translate" | "rotate" | "scale";

/** Child→parent Euler pose in scene-local meters (XYZ degrees, Z-up). */
export type SceneEulerPose = {
  translation: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
};
