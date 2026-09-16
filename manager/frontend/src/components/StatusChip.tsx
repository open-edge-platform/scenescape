// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import "./StatusChip.css";

type Props = {
  children: ReactNode;
  tone?: "neutral" | "ok" | "bad";
  className?: string;
};

export function StatusChip({
  children,
  tone = "neutral",
  className = "",
}: Props) {
  const toneClass =
    tone === "ok"
      ? "ss-status-chip--ok"
      : tone === "bad"
        ? "ss-status-chip--bad"
        : "";
  return (
    <span className={`ss-status-chip ${toneClass} ${className}`.trim()}>
      {children}
    </span>
  );
}
