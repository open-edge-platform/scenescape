// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  inferDeleteLabel,
  postDjangoDelete,
} from "../lib/djangoDelete";

type PendingDelete = {
  url: string;
  title: string;
  body: ReactNode;
  fallbackHref: string;
};

type Options = {
  /** Root to intercept; defaults to document */
  root?: ParentNode | null;
  fallbackHref?: string;
};

/**
 * Intercepts Django delete-page links and shows an in-page confirm dialog instead.
 */
export function useDeleteLinkInterceptor(options: Options = {}) {
  const [pending, setPending] = useState<PendingDelete | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fallbackHref = options.fallbackHref || "/";

  useEffect(() => {
    const root = options.root ?? document;
    const onClick = (ev: Event) => {
      const target = ev.target as HTMLElement | null;
      if (!target) {
        return;
      }
      const link = target.closest("a[href]") as HTMLAnchorElement | null;
      if (!link?.href) {
        return;
      }
      const path = link.pathname || "";
      const isDelete =
        /\/(cam|singleton_sensor|child|scene|asset)\/delete\//.test(path);
      if (!isDelete) {
        return;
      }
      // Only intercept same-origin delete URLs
      if (link.origin !== window.location.origin) {
        return;
      }
      ev.preventDefault();
      ev.stopPropagation();
      const kind = inferDeleteLabel(path, link.textContent || link.title || "");
      const name =
        link.getAttribute("title")?.replace(/^Delete\s+/i, "") ||
        link.dataset.name ||
        kind;
      setError(null);
      setPending({
        url: link.href,
        title: `Delete ${kind}?`,
        body: (
          <>
            <p>
              Are you sure you want to delete <strong>{name}</strong>?
            </p>
            <p>This action cannot be undone.</p>
          </>
        ),
        fallbackHref,
      });
    };
    root.addEventListener("click", onClick, true);
    return () => root.removeEventListener("click", onClick, true);
  }, [options.root, fallbackHref]);

  const confirm = useCallback(async () => {
    if (!pending) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await postDjangoDelete(pending.url, pending.fallbackHref);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }, [pending]);

  const cancel = useCallback(() => {
    if (busy) {
      return;
    }
    setPending(null);
    setError(null);
  }, [busy]);

  const dialog = (
    <ConfirmDialog
      open={Boolean(pending)}
      title={pending?.title || "Confirm delete"}
      confirmLabel="Delete"
      danger
      busy={busy}
      onConfirm={confirm}
      onCancel={cancel}
    >
      {pending?.body}
      {error ? <p className="ss-confirm-error">{error}</p> : null}
    </ConfirmDialog>
  );

  return { dialog, openDelete: setPending, busy };
}
