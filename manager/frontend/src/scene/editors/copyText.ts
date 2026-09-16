// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Copy plain text; prefer toast bridge when available. */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  const value = text.trim();
  if (!value) {
    return false;
  }
  try {
    await navigator.clipboard.writeText(value);
    window.ssToast?.show("Copied to clipboard", "ok");
    return true;
  } catch {
    window.ssToast?.show("Could not copy to clipboard", "bad");
    return false;
  }
}
