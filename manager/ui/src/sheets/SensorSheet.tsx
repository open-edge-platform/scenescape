// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FormEvent } from "react";
import { Drawer } from "../components/Drawer";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
import { FormSection } from "../components/FormSection";
import { useFormDirty } from "../components/useFormDirty";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";

export type SceneOption = { id: string; name: string };

type Props = {
  open: boolean;
  mode: "create" | "edit";
  sceneId: string;
  scenes?: SceneOption[];
  sensorUid?: string | null;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

const TYPES = [
  { value: "environmental", label: "Environmental" },
  { value: "generic", label: "Generic" },
];

export function SensorSheet({
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
  const [singletonType, setSingletonType] = useState("environmental");
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
      setSingletonType("environmental");
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
      .getSensor(authToken, sensorUid)
      .then((s) => {
        if (cancelled) {
          return;
        }
        setSensorId(String(s.sensor_id || s.uid || sensorUid));
        setName(String(s.name || ""));
        setSingletonType(String(s.singleton_type || "environmental"));
        if (s.scene) {
          setScene(String(s.scene));
        }
        setLoaded(true);
        resetDirty();
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load sensor");
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
    const payload = {
      sensor_id: sensorId.trim(),
      name: name.trim(),
      scene: scene.trim(),
      singleton_type: singletonType,
    };
    try {
      if (mode === "create") {
        await api.createSensor(authToken, payload);
        toast.show("Sensor created", "ok");
      } else if (sensorUid) {
        await api.updateSensor(authToken, sensorUid, payload);
        toast.show("Sensor updated", "ok");
      }
      resetDirty();
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
      title={mode === "create" ? "New sensor" : "Edit sensor"}
      onClose={onClose}
      dirty={dirty}
      actions={
        <Button
          variant="primary"
          disabled={busy || !dirty}
          form="ss-sensor-sheet-form"
          type="submit"
          title={dirty ? "Save changes" : "No unsaved changes"}
          className={dirty ? "ss-btn--dirty" : undefined}
        >
          {busy
            ? "Saving…"
            : mode === "create"
              ? "Add sensor"
              : dirty
                ? "Save"
                : "Saved"}
        </Button>
      }
    >
      <form
        id="ss-sensor-sheet-form"
        className="ss-drawer-form"
        onSubmit={submit}
      >
        {error ? <p className="ss-drawer-error">{error}</p> : null}
        {scenes.length > 0 ? (
          <FormSection
            id="ss-sensor-placement"
            title="Placement"
            description="Scene that owns this sensor."
          >
            <SelectField
              id="ss-sensor-scene"
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
          id="ss-sensor-identity"
          title="Identity"
          description="Must match the telemetry source id."
        >
          <TextField
            id="ss-sensor-id"
            label="Sensor ID"
            value={sensorId}
            onChange={(ev) => {
              setSensorId(ev.target.value);
              markDirty();
            }}
            required
            disabled={busy}
          />
          <TextField
            id="ss-sensor-name"
            label="Name"
            value={name}
            onChange={(ev) => {
              setName(ev.target.value);
              markDirty();
            }}
            required
            disabled={busy}
          />
          <SelectField
            id="ss-sensor-type"
            label="Type"
            value={singletonType}
            onChange={(ev) => {
              setSingletonType(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </SelectField>
        </FormSection>
      </form>
    </Drawer>
  );
}
