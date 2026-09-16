// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import "./FormCard.css";

type Props = {
  children: ReactNode;
  wide?: boolean;
  className?: string;
};

export function FormCard({ children, wide = false, className = "" }: Props) {
  return (
    <div
      className={`ss-form-card${wide ? " ss-form-card--wide" : ""} ${className}`.trim()}
    >
      <div className="ss-form-body">{children}</div>
    </div>
  );
}
