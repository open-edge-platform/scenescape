// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useAppToast } from "../components/ToastProvider";
import "./CalibrateOverlay.css";

type Props = {
  open: boolean;
  kind: "cam" | "sensor" | "scene";
  /** Database pk (cam/sensor) or scene uuid for scene manage */
  entityPk: string;
  title?: string;
  onClose: () => void;
};

function defaultTitle(kind: Props["kind"]): string {
  if (kind === "scene") {
    return "Manage scene";
  }
  if (kind === "sensor") {
    return "Calibrate sensor";
  }
  return "Calibrate camera";
}

function savedToast(kind: Props["kind"]): string {
  if (kind === "scene") {
    return "Scene saved";
  }
  if (kind === "sensor") {
    return "Sensor calibration saved";
  }
  return "Camera calibration saved";
}

function embedSrc(kind: Props["kind"], entityPk: string): string {
  if (kind === "scene") {
    return `/scene/update/${entityPk}?embed=1`;
  }
  if (kind === "sensor") {
    return `/singleton_sensor/calibrate/${entityPk}?embed=1`;
  }
  return `/cam/calibrate/${entityPk}?embed=1`;
}

/**
 * Full-viewport overlay hosting legacy Django pages via embed iframe.
 * Target URLs must honor ?embed=1 (and skip sheet redirects where applicable).
 */
export function CalibrateOverlay({
  open,
  kind,
  entityPk,
  title,
  onClose,
}: Props) {
  const toast = useAppToast();
  const [confirmClose, setConfirmClose] = useState(false);
  const [dirty, setDirty] = useState(false);
  const heading = title || defaultTitle(kind);

  const requestClose = useCallback(() => {
    if (dirty) {
      setConfirmClose(true);
      return;
    }
    onClose();
  }, [dirty, onClose]);

  useEffect(() => {
    if (!open) {
      setConfirmClose(false);
      setDirty(false);
      return;
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        requestClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, requestClose]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) {
        return;
      }
      if (ev.data && ev.data.type === "ss-calibrate-dirty") {
        setDirty(true);
        return;
      }
      if (ev.data && ev.data.type === "ss-calibrate-cancel") {
        requestClose();
        return;
      }
      if (ev.data && ev.data.type === "ss-calibrate-done") {
        toast.show(savedToast(kind), "ok");
        onClose();
        window.dispatchEvent(new CustomEvent("ss-calibrate-saved"));
        window.setTimeout(() => {
          window.location.reload();
        }, 250);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose, toast, kind, requestClose]);

  if (!open || !entityPk) {
    return null;
  }

  const leaveLabel =
    kind === "scene" ? "Leave without saving?" : "Leave calibration?";
  const leaveBody =
    kind === "scene"
      ? "You may have unsaved scene changes. Leave without saving?"
      : "You may have unsaved calibration changes. Leave without saving?";

  return createPortal(
    <>
      <div className="ss-calibrate-overlay" role="dialog" aria-modal="true">
        <div className="ss-calibrate-overlay-bar">
          <button
            type="button"
            className="ss-calibrate-overlay-back"
            aria-label={`Back from ${heading}`}
            onClick={requestClose}
          >
            <span className="ss-calibrate-overlay-back-icon" aria-hidden="true">
              ←
            </span>
            Back
          </button>
          <h2 className="ss-calibrate-overlay-title">{heading}</h2>
        </div>
        <iframe
          className="ss-calibrate-overlay-frame"
          title={heading}
          src={embedSrc(kind, entityPk)}
        />
      </div>
      <ConfirmDialog
        open={confirmClose}
        title={leaveLabel}
        confirmLabel="Leave"
        cancelLabel="Stay"
        danger
        onConfirm={() => {
          setConfirmClose(false);
          onClose();
        }}
        onCancel={() => setConfirmClose(false)}
      >
        <p>{leaveBody}</p>
      </ConfirmDialog>
    </>,
    document.body,
  );
}
