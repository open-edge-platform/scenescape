// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FormEvent } from "react";
import { Drawer } from "../components/Drawer";
import { TextField } from "../components/TextField";
import { Button } from "../components/Button";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";

type Props = {
  open: boolean;
  mode: "create" | "edit";
  assetUid?: string | null;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

export function AssetSheet({
  open,
  mode,
  assetUid,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [name, setName] = useState("");
  const [modelFile, setModelFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setModelFile(null);
    if (mode === "create") {
      setName("");
      return;
    }
    if (!assetUid) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    api
      .getAsset(authToken, assetUid)
      .then((a) => {
        if (!cancelled) {
          setName(String(a.name || ""));
        }
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load asset");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, mode, assetUid, authToken]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("name", name.trim());
    if (modelFile) {
      form.append("model_3d", modelFile);
    }
    try {
      if (mode === "create") {
        if (!modelFile) {
          setError("A .glb model file is required");
          setBusy(false);
          return;
        }
        await api.createAsset(authToken, form);
        toast.show("Asset created", "ok");
      } else if (assetUid) {
        await api.updateAsset(authToken, assetUid, form);
        toast.show("Asset updated", "ok");
      }
      onSaved();
      onClose();
    } catch (err) {
      setError((err as RestError).message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      open={open}
      title={mode === "create" ? "New 3D asset" : "Edit 3D asset"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={busy}
            form="ss-asset-sheet-form"
            type="submit"
          >
            {busy ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <form
        id="ss-asset-sheet-form"
        className="ss-drawer-form"
        onSubmit={submit}
      >
        {error ? <p className="ss-drawer-error">{error}</p> : null}
        <TextField
          id="ss-asset-name"
          label="Name"
          value={name}
          onChange={(ev) => setName(ev.target.value)}
          required
          disabled={busy}
        />
        <div className="ss-text-field">
          <label className="ss-text-field-label" htmlFor="ss-asset-glb">
            GLB model
          </label>
          <div className="ss-text-field-control">
            <input
              id="ss-asset-glb"
              type="file"
              accept=".glb,model/gltf-binary"
              disabled={busy}
              onChange={(ev) => setModelFile(ev.target.files?.[0] || null)}
            />
          </div>
        </div>
      </form>
    </Drawer>
  );
}
