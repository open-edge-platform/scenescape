// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import "./Card.css";

type Props = {
  children: ReactNode;
  className?: string;
};

export function Card({ children, className = "" }: Props) {
  return (
    <div className={`ss-card ${className}`.trim()}>
      <div className="ss-card-body">{children}</div>
    </div>
  );
}
