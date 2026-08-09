// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Shared command-surface conventions for scene workspace sheets.
 *
 * - **drawer**: create / short identity edit (CameraSheet, SensorSheet, ChildSheet)
 * - **panel**: complex calibrate / manage editors (WorkspacePanel)
 *
 * Both use the same Escape / focus trap / dirty-leave / toast patterns.
 */
export type CommandSurfaceKind = "drawer" | "panel";

export function chooseCommandSurface(complexity: "simple" | "complex"): CommandSurfaceKind {
  return complexity === "complex" ? "panel" : "drawer";
}
