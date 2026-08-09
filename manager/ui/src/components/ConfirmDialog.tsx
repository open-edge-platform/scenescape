// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import "./Button.css";
import "./ConfirmDialog.css";

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** In-page confirm dialog (ViPPET-style) — replaces Django delete intermediate pages. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  danger = true,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        onCancel();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, busy, onCancel]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="ss-confirm" role="presentation" onClick={onCancel}>
      <div
        className="ss-confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ss-confirm-header">
          <h2 className="ss-confirm-title" id={titleId}>
            {title}
          </h2>
          <button
            type="button"
            className="ss-confirm-close"
            aria-label="Close"
            disabled={busy}
            onClick={onCancel}
          >
            ×
          </button>
        </div>
        <div className="ss-confirm-body">{children}</div>
        <div className="ss-confirm-footer">
          <button
            ref={cancelRef}
            type="button"
            className="ss-btn ss-btn--secondary"
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`ss-btn ${danger ? "ss-btn--danger-solid" : "ss-btn--primary"}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
