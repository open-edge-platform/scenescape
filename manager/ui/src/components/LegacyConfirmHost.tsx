// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ConfirmDialog } from "./ConfirmDialog";

export type LegacyConfirmRequest = {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type Pending = LegacyConfirmRequest & {
  resolve: (ok: boolean) => void;
};

type ConfirmFn = (req: LegacyConfirmRequest | string) => Promise<boolean>;

/**
 * Hosts ConfirmDialog for legacy jQuery/JS via window.ssConfirm(...).
 * Install on pages that already mount ToastProvider / scene islands.
 */
export function LegacyConfirmHost({ children }: { children?: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const ask = useCallback<ConfirmFn>((req) => {
    const normalized: LegacyConfirmRequest =
      typeof req === "string" ? { message: req } : req;
    return new Promise<boolean>((resolve) => {
      setPending({ ...normalized, resolve });
    });
  }, []);

  useEffect(() => {
    window.ssConfirm = ask;
    return () => {
      if (window.ssConfirm === ask) {
        delete window.ssConfirm;
      }
    };
  }, [ask]);

  const finish = useCallback(
    (ok: boolean) => {
      if (!pending) {
        return;
      }
      pending.resolve(ok);
      setPending(null);
    },
    [pending],
  );

  return (
    <>
      {children}
      <ConfirmDialog
        open={Boolean(pending)}
        title={pending?.title || "Confirm"}
        confirmLabel={pending?.confirmLabel || "OK"}
        cancelLabel={pending?.cancelLabel || "Cancel"}
        danger={pending?.danger !== false}
        onConfirm={() => finish(true)}
        onCancel={() => finish(false)}
      >
        <p>{pending?.message}</p>
      </ConfirmDialog>
    </>
  );
}

declare global {
  interface Window {
    ssConfirm?: ConfirmFn;
  }
}
