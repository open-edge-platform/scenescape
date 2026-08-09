// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FormEvent } from "react";
import { Drawer } from "../components/Drawer";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
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
  const [childType, setChildType] = useState<"local" | "remote">("local");
  const [childSceneId, setChildSceneId] = useState("");
  const [childName, setChildName] = useState("");
  const [remoteChildId, setRemoteChildId] = useState("");
  const [hostName, setHostName] = useState("");
  const [mqttUsername, setMqttUsername] = useState("");
  const [mqttPassword, setMqttPassword] = useState("");
  const [retrack, setRetrack] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    if (mode === "create") {
      setChildType("local");
      setChildSceneId("");
      setChildName("");
      setRemoteChildId("");
      setHostName("");
      setMqttUsername("");
      setMqttPassword("");
      setRetrack(true);
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
  }, [open, mode, childUid, authToken]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload: Record<string, unknown> = {
      parent: parentSceneId,
      child_type: childType,
      retrack,
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

  const otherScenes = scenes.filter((s) => s.id !== parentSceneId);

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
        <p className="ss-drawer-hint">
          Transform pose can still be refined from the map after linking.
        </p>
      </form>
    </Drawer>
  );
}
