// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { InputHTMLAttributes, ReactNode } from "react";
import "./TextField.css";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: ReactNode;
  labelId?: string;
  error?: ReactNode;
};

export function TextField({
  label,
  labelId,
  id,
  error,
  className = "",
  ...rest
}: Props) {
  const inputId = id || labelId || undefined;
  return (
    <div className="ss-text-field">
      <label className="ss-text-field-label" htmlFor={inputId} id={labelId}>
        {label}
      </label>
      <div className="ss-text-field-control">
        <input
          id={inputId}
          className={`form-control ss-text-field-input ${className}`.trim()}
          {...rest}
        />
        {error ? <div className="ss-text-field-error">{error}</div> : null}
      </div>
    </div>
  );
}
