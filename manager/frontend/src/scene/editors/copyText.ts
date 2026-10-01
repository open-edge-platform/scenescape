// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

type ToastShow = (text: string, tone?: "ok" | "bad" | "info") => void;

/** Copy plain text; optional toast callback (do not use window.ssToast from React). */
export async function copyTextToClipboard(
  text: string,
  toastShow?: ToastShow,
): Promise<boolean> {
  const value = text.trim();
  if (!value) {
    return false;
  }
  try {
    await navigator.clipboard.writeText(value);
    toastShow?.("Copied to clipboard", "ok");
    return true;
  } catch {
    toastShow?.("Could not copy to clipboard", "bad");
    return false;
  }
}
