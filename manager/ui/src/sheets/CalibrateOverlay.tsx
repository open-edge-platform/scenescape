// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import { createPortal } from "react-dom";
import "./CalibrateOverlay.css";

type Props = {
  open: boolean;
  kind: "cam" | "sensor";
  /** Database pk used by Django calibrate URLs */
  entityPk: string;
  title?: string;
  onClose: () => void;
};

/**
 * Full-viewport overlay hosting legacy calibrate pages via embed iframe.
 * Calibrate URLs must honor ?embed=1 and skip redirect-to-sheet.
 */
export function CalibrateOverlay({
  open,
  kind,
  entityPk,
  title,
  onClose,
}: Props) {
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

  if (!open || !entityPk) {
    return null;
  }

  const src =
    kind === "cam"
      ? `/cam/calibrate/${entityPk}?embed=1`
      : `/singleton_sensor/calibrate/${entityPk}?embed=1`;

  return createPortal(
    <div className="ss-calibrate-overlay" role="dialog" aria-modal="true">
      <div className="ss-calibrate-overlay-bar">
        <h2 className="ss-calibrate-overlay-title">
          {title || (kind === "cam" ? "Calibrate camera" : "Calibrate sensor")}
        </h2>
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
        title={title || "Calibration"}
        src={src}
      />
    </div>,
    document.body,
  );
}
