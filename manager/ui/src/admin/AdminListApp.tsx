// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { PageHeader } from "../components/PageHeader";
import "./AdminListApp.css";

export type AdminListBootstrap = {
  title: string;
  breadcrumbs?: { label: string; href?: string }[];
  primaryAction?: { label: string; href: string; id?: string };
};

type Props = {
  bootstrap: AdminListBootstrap;
};

/** List page chrome island — table body stays Django-rendered below. */
export function AdminListApp({ bootstrap }: Props) {
  const actions = bootstrap.primaryAction ? (
    <a
      className="btn btn-primary"
      href={bootstrap.primaryAction.href}
      id={bootstrap.primaryAction.id}
    >
      {bootstrap.primaryAction.label}
    </a>
  ) : null;

  return (
    <div className="ss-admin-list-chrome hide-fullscreen">
      <PageHeader
        title={bootstrap.title}
        breadcrumbs={bootstrap.breadcrumbs || []}
        actions={actions}
      />
    </div>
  );
}
