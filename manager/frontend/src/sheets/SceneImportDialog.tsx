// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";

type Props = {
  open: boolean;
  authToken: string;
  onClose: () => void;
  onImported: () => void;
};

/** Import uses dialog chrome (upload), not a side drawer. */
export function SceneImportDialog({
  open,
  authToken,
  onClose,
  onImported,
}: Props) {
  const toast = useAppToast();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!file) {
      setError("Choose a scene zip file");
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("zipFile", file);
    try {
      await api.importScene(authToken, form);
      toast.show("Scene imported", "ok");
      onImported();
      onClose();
    } catch (err) {
      setError((err as RestError).message || "Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      title="Import scene"
      confirmLabel={busy ? "Importing…" : "Import"}
      cancelLabel="Cancel"
      danger={false}
      busy={busy}
      onConfirm={submit}
      onCancel={() => {
        if (!busy) {
          onClose();
        }
      }}
    >
      <p>Upload a SceneScape scene export (.zip).</p>
      <input
        type="file"
        accept=".zip,application/zip"
        disabled={busy}
        onChange={(ev) => setFile(ev.target.files?.[0] || null)}
      />
      {error ? <p className="ss-confirm-error">{error}</p> : null}
    </ConfirmDialog>
  );
}
