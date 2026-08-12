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
  parentSceneId: string;
  childUid?: string | null;
  scenes: SceneOption[];
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

type Vec3 = [string, string, string];

function str(v: unknown, fallback = "0"): string {
  if (v == null || v === "") {
    return fallback;
  }
  return String(v);
}

function vec3(arr: unknown, fallback: Vec3): Vec3 {
  if (Array.isArray(arr) && arr.length >= 3) {
    return [str(arr[0], fallback[0]), str(arr[1], fallback[1]), str(arr[2], fallback[2])];
  }
  return fallback;
}

function num(s: string, fallback = 0): number {
  const n = Number(s);
  return Number.isFinite(n) ? n : fallback;
}

export function ChildSheet({
  open,
  mode,
  parentSceneId,
  childUid,
  scenes,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [parentId, setParentId] = useState(parentSceneId);
  const [childType, setChildType] = useState<"local" | "remote">("local");
  const [childSceneId, setChildSceneId] = useState("");
  const [childName, setChildName] = useState("");
  const [remoteChildId, setRemoteChildId] = useState("");
  const [hostName, setHostName] = useState("");
  const [mqttUsername, setMqttUsername] = useState("");
  const [mqttPassword, setMqttPassword] = useState("");
  const [retrack, setRetrack] = useState(true);
  const [transformType, setTransformType] = useState("euler");
  const [translation, setTranslation] = useState<Vec3>(["0", "0", "0"]);
  const [rotation, setRotation] = useState<Vec3>(["0", "0", "0"]);
  const [scale, setScale] = useState<Vec3>(["1", "1", "1"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setParentId(parentSceneId);
    if (mode === "create") {
      setChildType("local");
      setChildSceneId("");
      setChildName("");
      setRemoteChildId("");
      setHostName("");
      setMqttUsername("");
      setMqttPassword("");
      setRetrack(true);
      setTransformType("euler");
      setTranslation(["0", "0", "0"]);
      setRotation(["0", "0", "0"]);
      setScale(["1", "1", "1"]);
      return;
    }
    if (!childUid) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    api
      .getChild(authToken, childUid)
      .then((c) => {
        if (cancelled) {
          return;
        }
        const ct = (c.child_type as string) === "remote" ? "remote" : "local";
        setChildType(ct);
        setChildSceneId(String(c.child || ""));
        setChildName(String(c.child_name || c.name || ""));
        setRemoteChildId(String(c.remote_child_id || ""));
        setHostName(String(c.host_name || ""));
        setMqttUsername(String(c.mqtt_username || ""));
        setRetrack(c.retrack !== false && c.retrack !== "false");
        const tt = String(c.transform_type || "euler");
        setTransformType(tt === "quaternion" || tt === "matrix" ? tt : "euler");
        const pose =
          c.transform && typeof c.transform === "object"
            ? (c.transform as Record<string, unknown>)
            : null;
        if (pose) {
          setTranslation(vec3(pose.translation, ["0", "0", "0"]));
          setRotation(vec3(pose.rotation, ["0", "0", "0"]));
          setScale(vec3(pose.scale, ["1", "1", "1"]));
        } else {
          setTranslation([
            str(c.transform1, "0"),
            str(c.transform2, "0"),
            str(c.transform3, "0"),
          ]);
          setRotation([
            str(c.transform4, "0"),
            str(c.transform5, "0"),
            str(c.transform6, "0"),
          ]);
          setScale([
            str(c.transform7, "1"),
            str(c.transform8, "1"),
            str(c.transform9, "1"),
          ]);
        }
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load child");
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
  }, [open, mode, childUid, authToken, parentSceneId]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const parent = parentId.trim() || parentSceneId.trim();
    if (!parent) {
      setError("Select a parent scene");
      setBusy(false);
      return;
    }
    const payload: Record<string, unknown> = {
      parent,
      child_type: childType,
      retrack,
      transform_type: transformType === "matrix" ? "matrix" : "euler",
      transform1: num(translation[0]),
      transform2: num(translation[1]),
      transform3: num(translation[2]),
      transform4: num(rotation[0]),
      transform5: num(rotation[1]),
      transform6: num(rotation[2]),
      transform7: num(scale[0], 1),
      transform8: num(scale[1], 1),
      transform9: num(scale[2], 1),
      transform10: 0,
      transform11: 1,
      transform12: 0,
      transform13: 0,
      transform14: 0,
      transform15: 0,
      transform16: 1,
    };
    if (childType === "local") {
      payload.child = childSceneId;
    } else {
      payload.child_name = childName.trim();
      payload.remote_child_id = remoteChildId.trim();
      payload.host_name = hostName.trim();
      payload.mqtt_username = mqttUsername.trim();
      if (mqttPassword) {
        payload.mqtt_password = mqttPassword;
      }
    }
    try {
      if (mode === "create") {
        await api.createChild(authToken, payload);
        toast.show("Child scene linked", "ok");
      } else if (childUid) {
        await api.updateChild(authToken, childUid, payload);
        toast.show("Child scene updated", "ok");
      }
      onSaved();
      onClose();
    } catch (err) {
      setError((err as RestError).message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const resolvedParent = parentId.trim() || parentSceneId.trim();
  const otherScenes = scenes.filter((s) => s.id !== resolvedParent);
  const showParentPicker = !parentSceneId.trim();

  return (
    <Drawer
      open={open}
      title={mode === "create" ? "Link child scene" : "Edit child link"}
      onClose={onClose}
      wide
      actions={
        <Button
          variant="primary"
          disabled={busy}
          form="ss-child-sheet-form"
          type="submit"
        >
          {busy ? "Saving…" : "Save"}
        </Button>
      }
    >
      <form
        id="ss-child-sheet-form"
        className="ss-drawer-form"
        onSubmit={submit}
      >
        {error ? <p className="ss-drawer-error">{error}</p> : null}
        {showParentPicker ? (
          <SelectField
            id="ss-child-parent"
            label="Parent scene"
            value={parentId}
            onChange={(ev) => setParentId(ev.target.value)}
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
        ) : null}
        <SelectField
          id="ss-child-type"
          label="Child type"
          value={childType}
          onChange={(ev) =>
            setChildType(ev.target.value === "remote" ? "remote" : "local")
          }
          disabled={busy}
        >
          <option value="local">Local</option>
          <option value="remote">Remote</option>
        </SelectField>
        {childType === "local" ? (
          <SelectField
            id="ss-child-scene"
            label="Child scene"
            value={childSceneId}
            onChange={(ev) => setChildSceneId(ev.target.value)}
            required
            disabled={busy}
          >
            <option value="">Select scene…</option>
            {otherScenes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        ) : (
          <>
            <TextField
              id="ss-child-name"
              label="Child name"
              value={childName}
              onChange={(ev) => setChildName(ev.target.value)}
              required
              disabled={busy}
            />
            <TextField
              id="ss-remote-child-id"
              label="Remote child ID"
              value={remoteChildId}
              onChange={(ev) => setRemoteChildId(ev.target.value)}
              required
              disabled={busy}
            />
            <TextField
              id="ss-host-name"
              label="Host name"
              value={hostName}
              onChange={(ev) => setHostName(ev.target.value)}
              required
              disabled={busy}
            />
            <TextField
              id="ss-mqtt-user"
              label="MQTT username"
              value={mqttUsername}
              onChange={(ev) => setMqttUsername(ev.target.value)}
              required
              disabled={busy}
            />
            <TextField
              id="ss-mqtt-pass"
              label="MQTT password"
              type="password"
              value={mqttPassword}
              onChange={(ev) => setMqttPassword(ev.target.value)}
              required={mode === "create"}
              disabled={busy}
              autoComplete="new-password"
            />
          </>
        )}
        <label className="ss-check-row">
          <input
            type="checkbox"
            checked={retrack}
            disabled={busy}
            onChange={(ev) => setRetrack(ev.target.checked)}
          />
          Retrack objects when they enter this parent
        </label>
        <FormSection
          title="Transform"
          description="Child pose relative to the parent scene (Euler)."
          collapsible
          defaultOpen={mode === "edit"}
          className="ss-form-section--columns"
        >
          <TextField
            id="ss-child-tx"
            label="Translation X (m)"
            value={translation[0]}
            onChange={(ev) =>
              setTranslation([ev.target.value, translation[1], translation[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-child-ty"
            label="Translation Y (m)"
            value={translation[1]}
            onChange={(ev) =>
              setTranslation([translation[0], ev.target.value, translation[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-child-tz"
            label="Translation Z (m)"
            value={translation[2]}
            onChange={(ev) =>
              setTranslation([translation[0], translation[1], ev.target.value])
            }
            disabled={busy}
          />
          <TextField
            id="ss-child-rx"
            label="Rotation X (°)"
            value={rotation[0]}
            onChange={(ev) =>
              setRotation([ev.target.value, rotation[1], rotation[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-child-ry"
            label="Rotation Y (°)"
            value={rotation[1]}
            onChange={(ev) =>
              setRotation([rotation[0], ev.target.value, rotation[2]])
            }
            disabled={busy}
          />
          <TextField
            id="ss-child-rz"
            label="Rotation Z (°)"
            value={rotation[2]}
            onChange={(ev) =>
              setRotation([rotation[0], rotation[1], ev.target.value])
            }
            disabled={busy}
          />
          <TextField
            id="ss-child-sx"
            label="Scale X"
            value={scale[0]}
            onChange={(ev) => setScale([ev.target.value, scale[1], scale[2]])}
            disabled={busy}
          />
          <TextField
            id="ss-child-sy"
            label="Scale Y"
            value={scale[1]}
            onChange={(ev) => setScale([scale[0], ev.target.value, scale[2]])}
            disabled={busy}
          />
          <TextField
            id="ss-child-sz"
            label="Scale Z"
            value={scale[2]}
            onChange={(ev) => setScale([scale[0], scale[1], ev.target.value])}
            disabled={busy}
          />
        </FormSection>
      </form>
    </Drawer>
  );
}
