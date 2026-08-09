// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import { PageHeader } from "../components/PageHeader";
import { FormCard } from "../components/FormCard";
import "./AdminFormApp.css";

export type AdminFormBootstrap = {
  title: string;
  breadcrumbs: { label: string; href?: string }[];
  wide?: boolean;
};

type Props = {
  bootstrap: AdminFormBootstrap;
};

/**
 * Adopts Django-rendered form markup into FormCard chrome (island, no SPA).
 */
export function AdminFormApp({ bootstrap }: Props) {
  const slotRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const slot = slotRef.current;
    const host = document.getElementById("ss-form-host");
    if (!slot || !host) {
      return;
    }
    slot.appendChild(host);
    host.hidden = false;
    return () => {
      const parking = document.getElementById("ss-form-parking");
      if (parking && host.parentElement === slot) {
        parking.appendChild(host);
        host.hidden = true;
      }
    };
  }, []);

  return (
    <div className="ss-admin-form">
      <PageHeader title={bootstrap.title} breadcrumbs={bootstrap.breadcrumbs} />
      <FormCard wide={Boolean(bootstrap.wide)}>
        <div ref={slotRef} className="ss-admin-form-slot" />
      </FormCard>
    </div>
  );
}
