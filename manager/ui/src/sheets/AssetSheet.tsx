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
  const [shiftType, setShiftType] = useState("1");
  const [projectToMap, setProjectToMap] = useState(false);
  const [rotationFromVelocity, setRotationFromVelocity] = useState(false);
  const [xBuffer, setXBuffer] = useState("0");
  const [yBuffer, setYBuffer] = useState("0");
  const [zBuffer, setZBuffer] = useState("0");
  const [rotation, setRotation] = useState<[string, string, string]>([
    "0",
    "0",
    "0",
  ]);
  const [translation, setTranslation] = useState<[string, string, string]>([
    "0",
    "0",
    "0",
  ]);
  const [mass, setMass] = useState("1");
  const [isStatic, setIsStatic] = useState(false);
  const [ttl, setTtl] = useState("0");
  const [linearDamping, setLinearDamping] = useState("0.05");
  const [angularDamping, setAngularDamping] = useState("0.05");
  const [restitution, setRestitution] = useState("0.5");
  const [centerOfMass, setCenterOfMass] = useState<[string, string, string]>([
    "0",
    "0",
    "0",
  ]);
  const [geometricCenter, setGeometricCenter] = useState<
    [string, string, string]
  >(["0", "0", "0"]);
  const [friction, setFriction] = useState<[string, string]>(["0.5", "0.4"]);
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
      setShiftType("1");
      setProjectToMap(false);
      setRotationFromVelocity(false);
      setXBuffer("0");
      setYBuffer("0");
      setZBuffer("0");
      setRotation(["0", "0", "0"]);
      setTranslation(["0", "0", "0"]);
      setMass("1");
      setIsStatic(false);
      setTtl("0");
      setLinearDamping("0.05");
      setAngularDamping("0.05");
      setRestitution("0.5");
      setCenterOfMass(["0", "0", "0"]);
      setGeometricCenter(["0", "0", "0"]);
      setFriction(["0.5", "0.4"]);
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
        const shift = a.shift_type;
        if (shift === "center" || shift === 1 || shift === "1") {
          setShiftType("1");
        } else if (shift === "bottom" || shift === 2 || shift === "2") {
          setShiftType("2");
        } else {
          setShiftType(str(shift, "1"));
        }
        setProjectToMap(Boolean(a.project_to_map));
        setRotationFromVelocity(Boolean(a.rotation_from_velocity));
        setXBuffer(a.x_buffer_size != null ? str(a.x_buffer_size) : "0");
        setYBuffer(a.y_buffer_size != null ? str(a.y_buffer_size) : "0");
        setZBuffer(a.z_buffer_size != null ? str(a.z_buffer_size) : "0");
        setRotation([
          a.rotation_x != null ? str(a.rotation_x) : "0",
          a.rotation_y != null ? str(a.rotation_y) : "0",
          a.rotation_z != null ? str(a.rotation_z) : "0",
        ]);
        setTranslation([
          a.translation_x != null ? str(a.translation_x) : "0",
          a.translation_y != null ? str(a.translation_y) : "0",
          a.translation_z != null ? str(a.translation_z) : "0",
        ]);
        setMass(a.mass != null ? str(a.mass) : "1");
        setIsStatic(Boolean(a.is_static));
        setTtl(a.ttl != null ? str(a.ttl) : "0");
        setLinearDamping(
          a.linear_damping != null ? str(a.linear_damping) : "0.05",
        );
        setAngularDamping(
          a.angular_damping != null ? str(a.angular_damping) : "0.05",
        );
        setRestitution(
          a.coefficient_of_restitution != null
            ? str(a.coefficient_of_restitution)
            : "0.5",
        );
        const com = Array.isArray(a.center_of_mass) ? a.center_of_mass : [0, 0, 0];
        setCenterOfMass([str(com[0], "0"), str(com[1], "0"), str(com[2], "0")]);
        const geo = Array.isArray(a.geometric_center)
          ? a.geometric_center
          : [0, 0, 0];
        setGeometricCenter([
          str(geo[0], "0"),
          str(geo[1], "0"),
          str(geo[2], "0"),
        ]);
        const fr = Array.isArray(a.friction_coefficients)
          ? a.friction_coefficients
          : [0.5, 0.4];
        setFriction([str(fr[0], "0.5"), str(fr[1], "0.4")]);
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
    form.append("x_buffer_size", xBuffer.trim() || "0");
    form.append("y_buffer_size", yBuffer.trim() || "0");
    form.append("z_buffer_size", zBuffer.trim() || "0");
    form.append("rotation_x", rotation[0].trim() || "0");
    form.append("rotation_y", rotation[1].trim() || "0");
    form.append("rotation_z", rotation[2].trim() || "0");
    form.append("translation_x", translation[0].trim() || "0");
    form.append("translation_y", translation[1].trim() || "0");
    form.append("translation_z", translation[2].trim() || "0");
    form.append("mass", mass.trim() || "1");
    form.append("is_static", isStatic ? "true" : "false");
    form.append("ttl", ttl.trim() || "0");
    form.append("linear_damping", linearDamping.trim() || "0.05");
    form.append("angular_damping", angularDamping.trim() || "0.05");
    form.append("coefficient_of_restitution", restitution.trim() || "0.5");
    form.append(
      "geometric_center",
      JSON.stringify(geometricCenter.map((v) => Number(v) || 0)),
    );
    form.append(
      "center_of_mass",
      JSON.stringify(centerOfMass.map((v) => Number(v) || 0)),
    );
    form.append(
      "friction_coefficients",
      JSON.stringify(friction.map((v) => Number(v) || 0)),
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
            <option value="1">Center</option>
            <option value="2">Bottom</option>
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
        <FormSection
          title="Buffers & pose"
          description="Collision buffers and model pose offsets."
          collapsible
          defaultOpen={false}
          className="ss-form-section--columns"
        >
          <TextField
            id="ss-asset-xbuf"
            label="X buffer"
            value={xBuffer}
            onChange={(ev) => setXBuffer(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-ybuf"
            label="Y buffer"
            value={yBuffer}
            onChange={(ev) => setYBuffer(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-zbuf"
            label="Z buffer"
            value={zBuffer}
            onChange={(ev) => setZBuffer(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-rx"
            label="Rotation X (°)"
            value={rotation[0]}
            onChange={(ev) => setRotation([ev.target.value, rotation[1], rotation[2]])}
            disabled={busy}
          />
          <TextField
            id="ss-asset-ry"
            label="Rotation Y (°)"
            value={rotation[1]}
            onChange={(ev) => setRotation([rotation[0], ev.target.value, rotation[2]])}
            disabled={busy}
          />
          <TextField
            id="ss-asset-rz"
            label="Rotation Z (°)"
            value={rotation[2]}
            onChange={(ev) => setRotation([rotation[0], rotation[1], ev.target.value])}
            disabled={busy}
          />
          <TextField
            id="ss-asset-tx"
            label="Translation X (m)"
            value={translation[0]}
            onChange={(ev) =>
              setTranslation([ev.target.value, translation[1], translation[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-ty"
            label="Translation Y (m)"
            value={translation[1]}
            onChange={(ev) =>
              setTranslation([translation[0], ev.target.value, translation[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-tz"
            label="Translation Z (m)"
            value={translation[2]}
            onChange={(ev) =>
              setTranslation([translation[0], translation[1], ev.target.value])
            }
            disabled={busy}
          />
        </FormSection>
        <FormSection
          title="Physics"
          description="Mass, damping, friction, and track lifetime."
          collapsible
          defaultOpen={false}
          className="ss-form-section--columns"
        >
          <TextField
            id="ss-asset-mass"
            label="Mass (kg)"
            value={mass}
            onChange={(ev) => setMass(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-ttl"
            label="TTL (s, 0 = infinite)"
            value={ttl}
            onChange={(ev) => setTtl(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-lin-damp"
            label="Linear damping"
            value={linearDamping}
            onChange={(ev) => setLinearDamping(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-ang-damp"
            label="Angular damping"
            value={angularDamping}
            onChange={(ev) => setAngularDamping(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-restitution"
            label="Restitution"
            value={restitution}
            onChange={(ev) => setRestitution(ev.target.value)}
            disabled={busy}
          />
          <TextField
            id="ss-asset-fric-s"
            label="Static friction"
            value={friction[0]}
            onChange={(ev) => setFriction([ev.target.value, friction[1]])}
            disabled={busy}
          />
          <TextField
            id="ss-asset-fric-d"
            label="Dynamic friction"
            value={friction[1]}
            onChange={(ev) => setFriction([friction[0], ev.target.value])}
            disabled={busy}
          />
          <TextField
            id="ss-asset-com-x"
            label="Center of mass X"
            value={centerOfMass[0]}
            onChange={(ev) =>
              setCenterOfMass([ev.target.value, centerOfMass[1], centerOfMass[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-com-y"
            label="Center of mass Y"
            value={centerOfMass[1]}
            onChange={(ev) =>
              setCenterOfMass([centerOfMass[0], ev.target.value, centerOfMass[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-com-z"
            label="Center of mass Z"
            value={centerOfMass[2]}
            onChange={(ev) =>
              setCenterOfMass([centerOfMass[0], centerOfMass[1], ev.target.value])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-geo-x"
            label="Geometric center X"
            value={geometricCenter[0]}
            onChange={(ev) =>
              setGeometricCenter([
                ev.target.value,
                geometricCenter[1],
                geometricCenter[2],
              ])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-geo-y"
            label="Geometric center Y"
            value={geometricCenter[1]}
            onChange={(ev) =>
              setGeometricCenter([
                geometricCenter[0],
                ev.target.value,
                geometricCenter[2],
              ])
            }
            disabled={busy}
          />
          <TextField
            id="ss-asset-geo-z"
            label="Geometric center Z"
            value={geometricCenter[2]}
            onChange={(ev) =>
              setGeometricCenter([
                geometricCenter[0],
                geometricCenter[1],
                ev.target.value,
              ])
            }
            disabled={busy}
          />
          <label className="ss-check-row">
            <input
              type="checkbox"
              checked={isStatic}
              disabled={busy}
              onChange={(ev) => setIsStatic(ev.target.checked)}
            />
            Static object
          </label>
        </FormSection>
      </form>
    </Drawer>
  );
}
