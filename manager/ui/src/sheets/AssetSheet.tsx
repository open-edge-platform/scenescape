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

type Props = {
  open: boolean;
  mode: "create" | "edit";
  assetUid?: string | null;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

function str(v: unknown, fallback = ""): string {
  if (v == null) {
    return fallback;
  }
  return String(v);
}

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
  const [markColor, setMarkColor] = useState("#00ff00");
  const [scale, setScale] = useState("1");
  const [xSize, setXSize] = useState("1");
  const [ySize, setYSize] = useState("1");
  const [zSize, setZSize] = useState("1");
  const [trackingRadius, setTrackingRadius] = useState("1");
  const [shiftType, setShiftType] = useState("center");
  const [projectToMap, setProjectToMap] = useState(false);
  const [rotationFromVelocity, setRotationFromVelocity] = useState(false);
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
      setMarkColor("#00ff00");
      setScale("1");
      setXSize("1");
      setYSize("1");
      setZSize("1");
      setTrackingRadius("1");
      setShiftType("center");
      setProjectToMap(false);
      setRotationFromVelocity(false);
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
        if (cancelled) {
          return;
        }
        setName(str(a.name));
        setMarkColor(str(a.mark_color, "#00ff00"));
        setScale(a.scale != null ? str(a.scale) : "1");
        setXSize(a.x_size != null ? str(a.x_size) : "1");
        setYSize(a.y_size != null ? str(a.y_size) : "1");
        setZSize(a.z_size != null ? str(a.z_size) : "1");
        setTrackingRadius(
          a.tracking_radius != null ? str(a.tracking_radius) : "1",
        );
        setShiftType(str(a.shift_type, "center"));
        setProjectToMap(Boolean(a.project_to_map));
        setRotationFromVelocity(Boolean(a.rotation_from_velocity));
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

  const appendCommon = (form: FormData) => {
    form.append("name", name.trim());
    form.append("mark_color", markColor);
    form.append("scale", scale.trim() || "1");
    form.append("x_size", xSize.trim() || "1");
    form.append("y_size", ySize.trim() || "1");
    form.append("z_size", zSize.trim() || "1");
    form.append("tracking_radius", trackingRadius.trim() || "1");
    form.append("shift_type", shiftType);
    form.append("project_to_map", projectToMap ? "true" : "false");
    form.append(
      "rotation_from_velocity",
      rotationFromVelocity ? "true" : "false",
    );
    if (modelFile) {
      form.append("model_3d", modelFile);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    appendCommon(form);
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
      wide
      actions={
        <Button
          variant="primary"
          disabled={busy}
          form="ss-asset-sheet-form"
          type="submit"
        >
          {busy ? "Saving…" : "Save"}
        </Button>
      }
    >
      <form
        id="ss-asset-sheet-form"
        className="ss-drawer-form"
        onSubmit={submit}
      >
        {error ? <p className="ss-drawer-error">{error}</p> : null}
        <FormSection title="Identity" description="Name and 3D model file.">
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
              GLB model{mode === "create" ? "" : " (optional replace)"}
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
          <TextField
            id="ss-asset-color"
            label="Mark color"
            value={markColor}
            onChange={(ev) => setMarkColor(ev.target.value)}
            disabled={busy}
          />
        </FormSection>
        <FormSection title="Size" description="Object extents and scale.">
          <TextField
            id="ss-asset-scale"
            label="Scale"
            value={scale}
            onChange={(ev) => setScale(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-x"
            label="X size"
            value={xSize}
            onChange={(ev) => setXSize(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-y"
            label="Y size"
            value={ySize}
            onChange={(ev) => setYSize(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-z"
            label="Z size"
            value={zSize}
            onChange={(ev) => setZSize(ev.target.value)}
            disabled={busy}
          />
        </FormSection>
        <FormSection
          title="Tracking"
          description="How detections map onto this object."
        >
          <TextField
            id="ss-asset-track-r"
            label="Tracking radius"
            value={trackingRadius}
            onChange={(ev) => setTrackingRadius(ev.target.value)}
            disabled={busy}
          />
          <SelectField
            id="ss-asset-shift"
            label="Shift type"
            value={shiftType}
            onChange={(ev) => setShiftType(ev.target.value)}
            disabled={busy}
          >
            <option value="center">Center</option>
            <option value="bottom">Bottom</option>
          </SelectField>
          <label className="ss-check-row">
            <input
              type="checkbox"
              checked={projectToMap}
              disabled={busy}
              onChange={(ev) => setProjectToMap(ev.target.checked)}
            />
            Project to map
          </label>
          <label className="ss-check-row">
            <input
              type="checkbox"
              checked={rotationFromVelocity}
              disabled={busy}
              onChange={(ev) => setRotationFromVelocity(ev.target.checked)}
            />
            Rotation from velocity
          </label>
        </FormSection>
      </form>
    </Drawer>
  );
}
