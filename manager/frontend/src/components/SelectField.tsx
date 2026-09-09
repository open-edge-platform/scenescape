// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode, SelectHTMLAttributes } from "react";
import "./TextField.css";

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  label: ReactNode;
  error?: ReactNode;
  children: ReactNode;
};

export function SelectField({
  label,
  id,
  error,
  children,
  className = "",
  ...rest
}: Props) {
  return (
    <div className="ss-text-field">
      <label className="ss-text-field-label" htmlFor={id}>
        {label}
      </label>
      <div className="ss-text-field-control">
        <select
          id={id}
          className={`form-control ss-select-field ${className}`.trim()}
          {...rest}
        >
          {children}
        </select>
        {error ? <div className="ss-text-field-error">{error}</div> : null}
      </div>
    </div>
  );
}
