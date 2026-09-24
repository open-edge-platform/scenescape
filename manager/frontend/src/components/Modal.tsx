// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import "./Modal.css";

type Props = {
  id: string;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose?: () => void;
};

/** Lightweight modal chrome; show/hide via Bootstrap data API or .show class. */
export function Modal({ id, title, children, footer, onClose }: Props) {
  return (
    <div
      className="modal fade ss-modal"
      id={id}
      tabIndex={-1}
      role="dialog"
      aria-labelledby={`${id}-title`}
      aria-hidden="true"
    >
      <div className="modal-dialog modal-dialog-centered" role="document">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title" id={`${id}-title`}>
              {title}
            </h5>
            <button
              type="button"
              className="close"
              data-dismiss="modal"
              aria-label="Close"
              onClick={onClose}
            >
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div className="modal-body">{children}</div>
          {footer ? <div className="modal-footer">{footer}</div> : null}
        </div>
      </div>
    </div>
  );
}
