// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { PageHeader } from "../components/PageHeader";
import "./AdminListApp.css";

export type AdminListAction = {
  label: string;
  href: string;
  tone?: "default" | "danger";
  id?: string;
};

export type AdminListCell = {
  text?: string;
  href?: string;
};

export type AdminListRow = {
  id: string;
  cells: AdminListCell[];
  actions?: AdminListAction[];
};

export type AdminListBootstrap = {
  title: string;
  breadcrumbs?: { label: string; href?: string }[];
  primaryAction?: { label: string; href: string; id?: string };
  columns: string[];
  rows: AdminListRow[];
  emptyMessage?: string;
  isSuperuser?: boolean;
};

type Props = {
  bootstrap: AdminListBootstrap;
};

/** Full list page: header + data table (Django supplies bootstrap JSON only). */
export function AdminListApp({ bootstrap }: Props) {
  const showActions =
    Boolean(bootstrap.isSuperuser) &&
    bootstrap.rows.some((r) => (r.actions || []).length > 0);

  const actions = bootstrap.primaryAction ? (
    <a
      className="ss-btn ss-btn--primary"
      href={bootstrap.primaryAction.href}
      id={bootstrap.primaryAction.id}
    >
      {bootstrap.primaryAction.label}
    </a>
  ) : null;

  return (
    <div className="ss-admin-list hide-fullscreen">
      <PageHeader
        title={bootstrap.title}
        breadcrumbs={bootstrap.breadcrumbs || []}
        actions={actions}
      />
      <div className="ss-table-card ss-admin-table-card">
        {bootstrap.rows.length === 0 ? (
          <p className="ss-table-empty">
            {bootstrap.emptyMessage || "Nothing to show."}
          </p>
        ) : (
          <table className="table table-fluid ss-admin-table">
            <thead>
              <tr>
                {bootstrap.columns.map((col) => (
                  <th key={col}>{col}</th>
                ))}
                {showActions ? <th>Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {bootstrap.rows.map((row) => (
                <tr key={row.id}>
                  {row.cells.map((cell, i) => (
                    <td key={`${row.id}-${i}`}>
                      {cell.href ? (
                        <a href={cell.href}>{cell.text || "—"}</a>
                      ) : (
                        cell.text || "—"
                      )}
                    </td>
                  ))}
                  {showActions ? (
                    <td>
                      <div className="ss-table-actions">
                        {(row.actions || []).map((action) => (
                          <a
                            key={`${row.id}-${action.label}-${action.href}`}
                            className={`ss-table-action${
                              action.tone === "danger" ? " is-danger" : ""
                            }`}
                            href={action.href}
                            id={action.id}
                            title={action.label}
                          >
                            <span>{action.label}</span>
                          </a>
                        ))}
                      </div>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
