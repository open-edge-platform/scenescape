// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import "./Drawer.css";
import "./Button.css";

type Props = {
  open: boolean;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  onClose: () => void;
};

/** Right-side sheet for in-page create/edit (ViPPET-style). */
export function Drawer({
  open,
  title,
  children,
  footer,
  wide = false,
  onClose,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
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

  if (!open) {
    return null;
  }

  return createPortal(
    <div className="ss-drawer-root is-open" role="presentation">
      <div className="ss-drawer-backdrop" onClick={onClose} />
      <aside
        className={`ss-drawer-panel${wide ? " ss-drawer-panel--wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="ss-drawer-header">
          <h2 className="ss-drawer-title" id={titleId}>
            {title}
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="ss-drawer-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="ss-drawer-body">{children}</div>
        {footer ? <div className="ss-drawer-footer">{footer}</div> : null}
      </aside>
    </div>,
    document.body,
  );
}
