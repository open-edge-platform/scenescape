// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { FormEvent, ReactNode } from "react";
import "./FormShell.css";

type Props = {
  id?: string;
  className?: string;
  error?: string | null;
  hint?: string | null;
  busy?: boolean;
  /** Sticky footer actions (Save / Cancel). */
  actions?: ReactNode;
  children: ReactNode;
  onSubmit: (ev: FormEvent) => void;
};

/**
 * Composable form chrome: body sections + optional sticky action bar.
 */
export function FormShell({
  id,
  className = "",
  error,
  hint,
  busy = false,
  actions,
  children,
  onSubmit,
}: Props) {
  const extra = className.trim();
  return (
    <form
      id={id}
      className={`ss-form-shell${actions ? " ss-form-shell--sticky" : ""}${extra ? ` ${extra}` : ""}`}
      onSubmit={onSubmit}
      aria-busy={busy || undefined}
    >
      <div className="ss-form-shell-body">
        {error ? <p className="ss-form-shell-error">{error}</p> : null}
        {hint ? <p className="ss-form-shell-hint">{hint}</p> : null}
        {children}
      </div>
      {actions ? (
        <div className="ss-form-shell-actions">{actions}</div>
      ) : null}
    </form>
  );
}
