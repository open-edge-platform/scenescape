// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import { createPortal } from "react-dom";
import "./CalibrateOverlay.css";

type Props = {
  open: boolean;
  /** Absolute or root-relative URL, already including embed=1 */
  src: string | null;
  title: string;
  onClose: () => void;
};

/**
 * Full-viewport overlay hosting a legacy Django form page via iframe.
 * Used for edit flows so the full form detail is preserved.
 */
export function EmbedFormOverlay({ open, src, title, onClose }: Props) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) {
        return;
      }
      if (ev.data && ev.data.type === "ss-calibrate-done") {
        onClose();
        window.location.reload();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose]);

  if (!open || !src) {
    return null;
  }

  return createPortal(
    <div className="ss-calibrate-overlay" role="dialog" aria-modal="true">
      <div className="ss-calibrate-overlay-bar">
        <h2 className="ss-calibrate-overlay-title">{title}</h2>
        <button
          type="button"
          className="ss-calibrate-overlay-close"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <iframe
        className="ss-calibrate-overlay-frame"
        title={title}
        src={src}
      />
    </div>,
    document.body,
  );
}

export function embedFormUrl(path: string): string {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("embed", "1");
  return url.pathname + url.search;
}
