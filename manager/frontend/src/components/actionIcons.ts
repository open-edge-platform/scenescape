// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Shared action icons — keep these consistent across Manager UI. */
export const ACTION_ICONS = {
  delete: "bi-trash",
  edit: "bi-pencil",
  configure: "bi-wrench",
} as const;

export type ActionIconKind = keyof typeof ACTION_ICONS;

/** Map common action labels to the shared icon set. */
export function iconForActionLabel(label: string): ActionIconKind | null {
  const key = label.trim().toLowerCase();
  if (key === "delete" || key === "remove") {
    return "delete";
  }
  if (key === "edit" || key === "update") {
    return "edit";
  }
  if (
    key === "configure" ||
    key === "manage" ||
    key === "calibrate" ||
    key === "settings"
  ) {
    return "configure";
  }
  return null;
}
