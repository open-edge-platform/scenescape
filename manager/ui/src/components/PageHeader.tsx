// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import "./PageHeader.css";

type Crumb = { label: string; href?: string };

type Props = {
  title: string;
  breadcrumbs?: Crumb[];
  actions?: ReactNode;
};

export function PageHeader({ title, breadcrumbs = [], actions }: Props) {
  return (
    <div className="ss-page-header hide-fullscreen">
      {breadcrumbs.length > 0 && (
        <nav aria-label="breadcrumb" className="ss-breadcrumb">
          <ol>
            {breadcrumbs.map((c, i) => (
              <li key={`${c.label}-${i}`}>
                {c.href ? (
                  <a href={c.href}>{c.label}</a>
                ) : (
                  <span>{c.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className="ss-page-header-row">
        <h2 className="ss-page-title" id="scene_name">
          {title}
        </h2>
        {actions ? (
          <div className="ss-page-header-actions">{actions}</div>
        ) : null}
      </div>
    </div>
  );
}
