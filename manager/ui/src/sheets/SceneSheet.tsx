// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FormEvent } from "react";
import { Drawer } from "../components/Drawer";
import { TextField } from "../components/TextField";
import { Button } from "../components/Button";
import { FormSection } from "../components/FormSection";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";

type Props = {
  open: boolean;
  mode: "create" | "edit";
  sceneUid?: string | null;
  authToken: string;
  onClose: () => void;
  onSaved: (sceneUid?: string) => void;
};

export function SceneSheet({
  open,
  mode,
  sceneUid,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [name, setName] = useState("");
  const [scale, setScale] = useState("100");
  const [mapFile, setMapFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setMapFile(null);
    if (mode === "create") {
      setName("");
      setScale("100");
      return;
    }
    if (!sceneUid) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    api
      .getScene(authToken, sceneUid)
      .then((s) => {
        if (cancelled) {
          return;
        }
        setName(String(s.name || ""));
        setScale(s.scale != null ? String(s.scale) : "100");
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load scene");
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
  }, [open, mode, sceneUid, authToken]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("name", name.trim());
    if (scale.trim()) {
      form.append("scale", scale.trim());
    }
    if (mapFile) {
      form.append("map", mapFile);
    }
    try {
      if (mode === "create") {
        const created = (await api.createScene(authToken, form)) as {
          uid?: string;
        };
        toast.show("Scene created", "ok");
        onSaved(created?.uid);
      } else if (sceneUid) {
        await api.updateScene(authToken, sceneUid, form);
        toast.show("Scene updated", "ok");
        onSaved(sceneUid);
      }
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
      title={mode === "create" ? "New scene" : "Edit scene"}
      onClose={onClose}
      wide
      actions={
        <Button
          variant="primary"
          disabled={busy}
          form="ss-scene-sheet-form"
          type="submit"
        >
          {busy ? "Saving…" : mode === "create" ? "Create scene" : "Save"}
        </Button>
      }
      footer={
        <Button variant="secondary" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      }
    >
      <form
        id="ss-scene-sheet-form"
        className="ss-drawer-form"
        onSubmit={submit}
      >
        {error ? <p className="ss-drawer-error">{error}</p> : null}
        <FormSection
          id="ss-scene-identity"
          title="Identity"
          description="How this scene appears in the gallery."
        >
          <TextField
            id="ss-scene-name"
            label="Name"
            value={name}
            onChange={(ev) => setName(ev.target.value)}
            required
            disabled={busy}
          />
        </FormSection>
        <FormSection
          id="ss-scene-map"
          title="Map"
          description="Floor plan and scale for the common create path."
        >
          <TextField
            id="ss-scene-scale"
            label="Scale (px per meter)"
            value={scale}
            onChange={(ev) => setScale(ev.target.value)}
            disabled={busy}
          />
          <div className="ss-text-field">
            <label className="ss-text-field-label" htmlFor="ss-scene-map">
              Map image
            </label>
            <div className="ss-text-field-control">
              <input
                id="ss-scene-map"
                type="file"
                accept="image/*,.pdf,.svg,.glb,.gltf"
                disabled={busy}
                onChange={(ev) => setMapFile(ev.target.files?.[0] || null)}
              />
            </div>
          </div>
          <p className="ss-drawer-hint">
            Geospatial providers and advanced calibration live under Manage
            Scene after create.
          </p>
        </FormSection>
      </form>
    </Drawer>
  );
}
