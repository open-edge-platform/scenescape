// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { ConfirmDialog } from "./ConfirmDialog";
import "./WorkspacePanel.css";

type Props = {
  open: boolean;
  title: string;
  children: ReactNode;
  /** Extra controls on the right of the top bar (e.g. Save). */
  actions?: ReactNode;
  /** Body layout: scroll form, full-bleed, or split main|aside. */
  layout?: "form" | "bleed" | "split";
  /** Extra class on the panel root (e.g. nested stacking). */
  className?: string;
  dirty?: boolean;
  leaveTitle?: string;
  leaveBody?: string;
  onClose: () => void;
};

/**
 * Full-viewport React workspace chrome (replaces Django iframe overlays).
 * Owns Back, Escape, and optional dirty-leave confirm.
 */
export function WorkspacePanel({
  open,
  title,
  children,
  actions,
  layout = "form",
  className,
  dirty = false,
  leaveTitle = "Leave without saving?",
  leaveBody = "You may have unsaved changes. Leave without saving?",
  onClose,
}: Props) {
  const titleId = useId();
  const [confirmClose, setConfirmClose] = useState(false);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const requestClose = useCallback(() => {
    if (dirtyRef.current) {
      setConfirmClose(true);
      return;
    }
    onCloseRef.current();
  }, []);

  useEffect(() => {
    if (!open) {
      setConfirmClose(false);
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

  if (!open) {
    return null;
  }

  const bodyClass =
    layout === "bleed"
      ? "ss-workspace-panel-body ss-workspace-panel-body--bleed"
      : layout === "split"
        ? "ss-workspace-panel-body ss-workspace-panel-body--split"
        : "ss-workspace-panel-body";

  return createPortal(
    <>
      <div
        className={`ss-workspace-panel${className ? ` ${className}` : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="ss-workspace-panel-bar">
          <div className="ss-workspace-panel-bar-start">
            <button
              type="button"
              className="ss-workspace-panel-back"
              aria-label={`Back from ${title}`}
              onClick={requestClose}
            >
              <span aria-hidden="true">←</span>
              Back
            </button>
            <h2 className="ss-workspace-panel-title" id={titleId}>
              {title}
            </h2>
          </div>
          {actions ? (
            <div className="ss-workspace-panel-actions">{actions}</div>
          ) : (
            <div className="ss-workspace-panel-actions" aria-hidden="true" />
          )}
        </div>
        <div className={bodyClass}>{children}</div>
      </div>
      <ConfirmDialog
        open={confirmClose}
        title={leaveTitle}
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
