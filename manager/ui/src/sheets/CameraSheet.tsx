// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FormEvent } from "react";
import { Drawer } from "../components/Drawer";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
import { FormSection } from "../components/FormSection";
import { FormShell } from "../components/FormShell";
import { useFormDirty } from "../components/useFormDirty";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";

export type SceneOption = { id: string; name: string };

type Props = {
  open: boolean;
  mode: "create" | "edit";
  sceneId: string;
  scenes?: SceneOption[];
  /** REST camera uid (sensor_id) for edit */
  sensorUid?: string | null;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

export function CameraSheet({
  open,
  mode,
  sceneId,
  scenes = [],
  sensorUid,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [sensorId, setSensorId] = useState("");
  const [name, setName] = useState("");
  const [scene, setScene] = useState(sceneId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(mode === "create");
  const { dirty, markDirty, resetDirty } = useFormDirty(loaded);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setScene(sceneId);
    resetDirty();
    if (mode === "create") {
      setSensorId("");
      setName("");
      setLoaded(true);
      return;
    }
    setLoaded(false);
    if (!sensorUid) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    api
      .getCamera(authToken, sensorUid)
      .then((cam) => {
        if (cancelled) {
          return;
        }
        setSensorId(String(cam.sensor_id || cam.uid || sensorUid));
        setName(String(cam.name || ""));
        if (cam.scene) {
          setScene(String(cam.scene));
        }
        setLoaded(true);
        resetDirty();
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load camera");
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
  }, [open, mode, sensorUid, authToken, sceneId, resetDirty]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!scene.trim()) {
      setError("Scene is required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        await api.createCamera(authToken, {
          sensor_id: sensorId.trim(),
          name: name.trim(),
          scene: scene.trim(),
        });
        toast.show("Camera created", "ok");
      } else if (sensorUid) {
        await api.updateCamera(authToken, sensorUid, {
          sensor_id: sensorId.trim(),
          name: name.trim(),
          scene: scene.trim(),
        });
        toast.show("Camera updated", "ok");
      }
      resetDirty();
      onSaved();
      onClose();
    } catch (err) {
      const re = err as RestError;
      setError(re.message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      open={open}
      title={mode === "create" ? "New camera" : "Edit camera"}
      onClose={onClose}
      dirty={dirty}
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={busy || !dirty}
            form="ss-cam-sheet-form"
            type="submit"
            title={dirty ? "Save changes" : "No unsaved changes"}
            className={dirty ? "ss-btn--dirty" : undefined}
          >
            {busy
              ? "Saving…"
              : mode === "create"
                ? "Add camera"
                : dirty
                  ? "Save"
                  : "Saved"}
          </Button>
        </>
      }
    >
      <FormShell
        id="ss-cam-sheet-form"
        className="ss-drawer-form"
        error={error}
        hint={
          busy && mode === "edit" && !loaded ? "Loading camera…" : null
        }
        busy={busy}
        onSubmit={submit}
      >
        {scenes.length > 0 ? (
          <FormSection
            id="ss-cam-placement"
            title="Placement"
            description="Scene that owns this camera."
          >
            <SelectField
              id="ss-cam-scene"
              label="Scene"
              value={scene}
              onChange={(ev) => {
                setScene(ev.target.value);
                markDirty();
              }}
              required
              disabled={busy}
            >
              <option value="">Select scene…</option>
              {scenes.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          </FormSection>
        ) : null}
        <FormSection
          id="ss-cam-identity"
          title="Identity"
          description="Must match the analytics pipeline camera id."
        >
          <TextField
            id="ss-cam-sensor-id"
            label="Camera ID"
            value={sensorId}
            onChange={(ev) => {
              setSensorId(ev.target.value);
              markDirty();
            }}
            required
            disabled={busy}
          />
          <TextField
            id="ss-cam-name"
            label="Name"
            value={name}
            onChange={(ev) => {
              setName(ev.target.value);
              markDirty();
            }}
            required
            disabled={busy}
          />
          <p className="ss-drawer-hint">
            Calibrate after creating so detections land correctly on the map.
          </p>
        </FormSection>
      </FormShell>
    </Drawer>
  );
}
