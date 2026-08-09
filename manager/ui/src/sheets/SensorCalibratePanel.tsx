// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { WorkspacePanel } from "../components/WorkspacePanel";
import { FormSection } from "../components/FormSection";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
import {
  PanelLayoutToggle,
  chooseAutoPanelLayout,
  readPanelLayoutMode,
  writePanelLayoutMode,
  type PanelLayout,
  type PanelLayoutMode,
} from "../components/PanelLayoutToggle";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";
import "./CameraCalibratePanel.css";
import "../components/PanelLayoutToggle.css";

type Props = {
  open: boolean;
  /** Django DB pk as string (from bootstrap sensors[].id) */
  sensorPk: string;
  /** sensor_id for REST (from bootstrap sensors[].sensorId) */
  sensorId: string;
  sceneId: string;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

const TYPES = [
  { value: "environmental", label: "Environmental" },
  { value: "generic", label: "Generic" },
];

/**
 * Full-viewport sensor calibrate panel.
 * Identity settings via REST; area / map ROI stay in the Django embed.
 */
export function SensorCalibratePanel({
  open,
  sensorPk,
  sensorId,
  sceneId,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [name, setName] = useState("");
  const [sensorIdEdit, setSensorIdEdit] = useState(sensorId);
  const [singletonType, setSingletonType] = useState("environmental");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [iframeDirty, setIframeDirty] = useState(false);
  const [layoutMode, setLayoutMode] = useState<PanelLayoutMode>(() =>
    typeof window !== "undefined" ? readPanelLayoutMode() : "auto",
  );
  const [autoLayout, setAutoLayout] = useState<PanelLayout>(() =>
    typeof window !== "undefined" ? chooseAutoPanelLayout() : "stack",
  );

  const resolvedLayout: PanelLayout =
    layoutMode === "auto" ? autoLayout : layoutMode;
  const restUid = sensorIdEdit.trim() || sensorId;

  const setPanelLayoutMode = useCallback((mode: PanelLayoutMode) => {
    setLayoutMode(mode);
    writePanelLayoutMode(mode);
  }, []);

  const pushLayoutToIframe = useCallback((layout: PanelLayout) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) {
      return;
    }
    win.postMessage(
      { type: "ss-calibrate-layout", layout },
      window.location.origin,
    );
  }, []);

  const markDirty = useCallback(() => {
    if (loaded) {
      setDirty(true);
    }
  }, [loaded]);

  useEffect(() => {
    const recompute = () => setAutoLayout(chooseAutoPanelLayout());
    recompute();
    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, []);

  useEffect(() => {
    if (!open || !sensorId) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);
    setDirty(false);
    setIframeDirty(false);
    setLoaded(false);
    setIframeReady(false);
    api
      .getSensor(authToken, sensorId)
      .then((s) => {
        if (cancelled) {
          return;
        }
        setName(String(s.name || ""));
        setSensorIdEdit(String(s.sensor_id || s.uid || sensorId));
        setSingletonType(String(s.singleton_type || "environmental"));
        setLoaded(true);
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
  }, [open, sensorId, authToken]);

  useEffect(() => {
    if (!open) {
      setDirty(false);
      setIframeDirty(false);
      setBusy(false);
      setIframeReady(false);
      return;
    }
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) {
        return;
      }
      if (!ev.data || typeof ev.data !== "object") {
        return;
      }
      const type = (ev.data as { type?: string }).type;
      if (type === "ss-calibrate-dirty") {
        setIframeDirty(true);
        setDirty(true);
        return;
      }
      if (type === "ss-calibrate-cancel") {
        onClose();
        return;
      }
      if (type === "ss-calibrate-done") {
        toast.show("Sensor calibration saved", "ok");
        setBusy(false);
        setDirty(false);
        setIframeDirty(false);
        onSaved();
        onClose();
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose, onSaved, toast]);

  useEffect(() => {
    if (!open || !iframeReady) {
      return;
    }
    pushLayoutToIframe(resolvedLayout);
  }, [open, iframeReady, resolvedLayout, pushLayoutToIframe]);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!restUid) {
      setError("Sensor id is missing");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.updateSensor(authToken, restUid, {
        name: name.trim(),
        sensor_id: restUid,
        scene: sceneId,
        singleton_type: singletonType,
      });
      if (iframeDirty || iframeReady) {
        iframeRef.current?.contentWindow?.postMessage(
          { type: "ss-calibrate-save-points" },
          window.location.origin,
        );
      }
      toast.show("Sensor saved", "ok");
      setDirty(false);
      onSaved();
      onClose();
    } catch (err) {
      setError((err as RestError).message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const formBody = (
    <form
      id="ss-sensor-calibrate-form"
      className="ss-workspace-panel-form"
      onSubmit={submit}
    >
      {error ? <p className="ss-workspace-panel-error">{error}</p> : null}
      {busy && !loaded ? (
        <p className="ss-workspace-panel-hint">Loading sensor…</p>
      ) : null}
      <FormSection
        id="ss-sensor-cal-identity"
        title="Identity"
        description="Sensor name and pipeline id. Area geometry stays in the map."
      >
        <TextField
          id="ss-sensor-cal-name"
          label="Name"
          value={name}
          onChange={(ev) => {
            setName(ev.target.value);
            markDirty();
          }}
          required
          disabled={busy}
        />
        <TextField
          id="ss-sensor-cal-id"
          label="Sensor ID"
          value={sensorIdEdit}
          onChange={(ev) => {
            setSensorIdEdit(ev.target.value);
            markDirty();
          }}
          required
          disabled={busy}
        />
        <SelectField
          id="ss-sensor-cal-type"
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
  );

  return (
    <WorkspacePanel
      open={open && Boolean(sensorPk)}
      title="Calibrate sensor"
      layout="bleed"
      dirty={dirty}
      leaveTitle="Leave calibration?"
      leaveBody="You may have unsaved calibration changes. Leave without saving?"
      onClose={onClose}
      actions={
        <>
          <PanelLayoutToggle
            layoutMode={layoutMode}
            onChange={setPanelLayoutMode}
          />
          <Button
            variant="primary"
            disabled={busy || !loaded || !dirty}
            form="ss-sensor-calibrate-form"
            type="submit"
            title={dirty ? "Save changes" : "No unsaved changes"}
            className={dirty ? "ss-btn--dirty" : undefined}
          >
            {busy ? "Saving…" : dirty ? "Save" : "Saved"}
          </Button>
        </>
      }
    >
      <div
        className={`ss-cal-workspace ss-cal-workspace--${resolvedLayout}`}
        data-cal-layout={resolvedLayout}
        data-cal-layout-mode={layoutMode}
      >
        <div className="ss-cal-workspace-main ss-workspace-cal-preview">
          <div className="ss-workspace-cal-preview-meta">
            <h3 className="ss-form-section-title">Area on map</h3>
            <p className="ss-workspace-panel-hint" style={{ marginBottom: 0 }}>
              Place the sensor area (scene, circle, or polygon) and occupancy
              color ranges on the scene map.
            </p>
          </div>
          {sensorPk ? (
            <div className="ss-workspace-cal-preview-frame">
              <iframe
                ref={iframeRef}
                title="Sensor calibrator"
                src={`/singleton_sensor/calibrate/${sensorPk}?embed=1`}
                onLoad={() => setIframeReady(true)}
              />
            </div>
          ) : (
            <p className="ss-workspace-panel-hint">
              Sensor primary key is missing; calibrator cannot load.
            </p>
          )}
        </div>
        <aside className="ss-cal-workspace-aside">{formBody}</aside>
      </div>
    </WorkspacePanel>
  );
}
