// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FormEvent } from "react";
import { Drawer } from "../components/Drawer";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
import { FormSection } from "../components/FormSection";
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

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setScene(sceneId);
    if (mode === "create") {
      setSensorId("");
      setName("");
      return;
    }
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
  }, [open, mode, sensorUid, authToken, sceneId]);

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
      footer={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={busy}
            form="ss-cam-sheet-form"
            type="submit"
          >
            {busy ? "Saving…" : mode === "create" ? "Add camera" : "Save"}
          </Button>
        </>
      }
    >
      <form id="ss-cam-sheet-form" className="ss-drawer-form" onSubmit={submit}>
        {error ? <p className="ss-drawer-error">{error}</p> : null}
        {busy && mode === "edit" && !name ? (
          <p className="ss-drawer-hint">Loading camera…</p>
        ) : null}
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
              onChange={(ev) => setScene(ev.target.value)}
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
            onChange={(ev) => setSensorId(ev.target.value)}
            required
            disabled={busy}
          />
          <TextField
            id="ss-cam-name"
            label="Name"
            value={name}
            onChange={(ev) => setName(ev.target.value)}
            required
            disabled={busy}
          />
          <p className="ss-drawer-hint">
            Calibrate after creating so detections land correctly on the map.
          </p>
        </FormSection>
      </form>
    </Drawer>
  );
}
