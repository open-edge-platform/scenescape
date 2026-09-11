// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import "./PageHeader.css";

type Crumb = { label: string; href?: string };

type BackLink = {
  href: string;
  /** Defaults to "Back". Prefer a parent name (e.g. "Scenes") on workspace pages. */
  label?: string;
};

type Props = {
  title: string;
  breadcrumbs?: Crumb[];
  back?: BackLink;
  /** Content immediately after the title (same main cluster as back + title). */
  titleEnd?: ReactNode;
  /** When false, omit the default title heading (use titleEnd to render it). */
  showTitle?: boolean;
  /** Centered chrome between the title cluster and right-side actions. */
  center?: ReactNode;
  actions?: ReactNode;
};

/** Drop crumbs that only echo the page title (and empty trails). */
function wayfindingCrumbs(crumbs: Crumb[], title: string): Crumb[] {
  if (!crumbs.length) {
    return [];
  }
  const trimmed = [...crumbs];
  const last = trimmed[trimmed.length - 1];
  if (last && !last.href && last.label === title) {
    trimmed.pop();
  }
  return trimmed;
}

export function PageHeader({
  title,
  breadcrumbs = [],
  back,
  titleEnd,
  showTitle = true,
  center,
  actions,
}: Props) {
  const crumbs = wayfindingCrumbs(breadcrumbs, title);
  const hasCenter = center != null;

  return (
    <div
      className={`ss-page-header${hasCenter ? "" : " hide-fullscreen"}`}
    >
      {crumbs.length > 0 ? (
        <nav
          aria-label="Breadcrumb"
          className="ss-breadcrumb hide-fullscreen"
        >
          <ol>
            {crumbs.map((c, i) => (
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
      ) : null}
      <div
        className={`ss-page-header-row${hasCenter ? " ss-page-header-row--split" : ""}`}
      >
        <div className="ss-page-header-main hide-fullscreen">
          {back ? (
            <a className="ss-form-back" href={back.href}>
              <span className="ss-form-back-icon" aria-hidden="true">
                ←
              </span>
              {back.label || "Back"}
            </a>
          ) : null}
          {showTitle ? (
            <h2 className="ss-page-title" id="scene_name">
              {title}
            </h2>
          ) : null}
          {titleEnd ? (
            <div className="ss-page-header-title-end">{titleEnd}</div>
          ) : null}
        </div>
        {hasCenter ? (
          <div className="ss-page-header-center">{center}</div>
        ) : null}
        {actions ? (
          <div className="ss-page-header-actions hide-fullscreen">
            {actions}
          </div>
        ) : null}
      </div>
    </div>
  );
}
