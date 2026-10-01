// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Read a Django `json_script` bootstrap payload by element id.
 * Contract: docs/design/manager-ui-backend-contract.md §5.1.
 */
export function readBootstrapJson<T>(elementId: string): T | null {
  const el = document.getElementById(elementId);
  if (!el?.textContent) {
    return null;
  }
  try {
    return JSON.parse(el.textContent) as T;
  } catch {
    console.error(`Failed to parse bootstrap JSON (#${elementId})`);
    return null;
  }
}
