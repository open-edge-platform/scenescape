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
  /** Django DB pk as string (from bootstrap cameras[].id) */
  cameraPk: string;
  /** sensor_id for REST (from bootstrap cameras[].sensorId) */
  sensorId: string;
  sceneId: string;
  authToken: string;
  /** Advanced pipeline fields only exist on Kubernetes deploys (matches CamCalibrateForm). */
  isKubernetes: boolean;
  onClose: () => void;
  onSaved: () => void;
};

type NumMap = Record<string, string>;

function numStr(v: unknown, fallback = ""): string {
  if (v === null || v === undefined || v === "") {
    return fallback;
  }
  return String(v);
}

function parseNum(s: string): number | undefined {
  const t = s.trim();
  if (!t) {
    return undefined;
  }
  const n = Number(t);
  return Number.isFinite(n) ? n : undefined;
}

function resolutionParts(resolution: unknown): { width: string; height: string } {
  if (Array.isArray(resolution) && resolution.length >= 2) {
    return { width: numStr(resolution[0]), height: numStr(resolution[1]) };
  }
  if (resolution && typeof resolution === "object") {
    const r = resolution as Record<string, unknown>;
    return { width: numStr(r.width), height: numStr(r.height) };
  }
  return { width: "", height: "" };
}

/**
 * Full-viewport camera calibrate / settings panel.
 * Persists settings via REST; point picking stays in a nested Django embed.
 */
export function CameraCalibratePanel({
  open,
  cameraPk,
  sensorId,
  sceneId,
  authToken,
  isKubernetes,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const lockFocalRef = useRef(true);
  const [layoutMode, setLayoutMode] = useState<PanelLayoutMode>(() =>
    typeof window !== "undefined" ? readPanelLayoutMode() : "auto",
  );
  const [autoLayout, setAutoLayout] = useState<PanelLayout>(() =>
    typeof window !== "undefined" ? chooseAutoPanelLayout() : "stack",
  );
  const [name, setName] = useState("");
  const [sensorIdEdit, setSensorIdEdit] = useState(sensorId);
  const [intrinsics, setIntrinsics] = useState<NumMap>({
    fx: "",
    fy: "",
    cx: "",
    cy: "",
  });
  const [distortion, setDistortion] = useState<NumMap>({
    k1: "",
    k2: "",
    p1: "",
    p2: "",
    k3: "",
  });
  /** When true, fx/fy are known constraints (not estimated). Matches main Lock value. */
  const [lockFocal, setLockFocal] = useState(true);
  const [width, setWidth] = useState("");
  const [height, setHeight] = useState("");
  const [cvSubsystem, setCvSubsystem] = useState("AUTO");
  const [undistort, setUndistort] = useState(false);
  const [modelconfig, setModelconfig] = useState("model_config.json");
  const [useCameraPipeline, setUseCameraPipeline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);

  lockFocalRef.current = lockFocal;
  const hasAdvanced = isKubernetes;
  const distortionEditable = isKubernetes;

  const markDirty = useCallback(() => {
    if (loaded) {
      setDirty(true);
    }
  }, [loaded]);

  const pushOpticsToIframe = useCallback(
    (nextIn: NumMap, nextDist: NumMap, locked: boolean) => {
      const win = iframeRef.current?.contentWindow;
      if (!win) {
        return;
      }
      win.postMessage(
        {
          type: "ss-calibrate-optics-set",
          intrinsics: nextIn,
          distortion: nextDist,
          fixIntrinsics: { fx: locked, fy: locked },
        },
        window.location.origin,
      );
    },
    [],
  );

  useEffect(() => {
    if (!open || !sensorId) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);
    setDirty(false);
    setLoaded(false);
    setLockFocal(true);
    setIframeReady(false);
    api
      .getCamera(authToken, sensorId)
      .then((cam) => {
        if (cancelled) {
          return;
        }
        setName(String(cam.name || ""));
        setSensorIdEdit(String(cam.sensor_id || cam.uid || sensorId));
        const inn =
          cam.intrinsics && typeof cam.intrinsics === "object"
            ? (cam.intrinsics as Record<string, unknown>)
            : {};
        setIntrinsics({
          fx: numStr(inn.fx),
          fy: numStr(inn.fy),
          cx: numStr(inn.cx),
          cy: numStr(inn.cy),
        });
        const dist =
          cam.distortion && typeof cam.distortion === "object"
            ? (cam.distortion as Record<string, unknown>)
            : {};
        setDistortion({
          k1: numStr(dist.k1),
          k2: numStr(dist.k2),
          p1: numStr(dist.p1),
          p2: numStr(dist.p2),
          k3: numStr(dist.k3),
        });
        const res = resolutionParts(cam.resolution);
        setWidth(res.width);
        setHeight(res.height);
        if (hasAdvanced) {
          setCvSubsystem(String(cam.cv_subsystem || "AUTO"));
          setUndistort(Boolean(cam.undistort));
          setModelconfig(String(cam.modelconfig || "model_config.json"));
          setUseCameraPipeline(Boolean(cam.use_camera_pipeline));
        }
        setLoaded(true);
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
  }, [open, sensorId, authToken, hasAdvanced]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) {
        return;
      }
      if (!ev.data || typeof ev.data !== "object") {
        return;
      }
      if (ev.data.type === "ss-calibrate-done") {
        toast.show("Camera calibration saved", "ok");
        onSaved();
        onClose();
        return;
      }
      if (ev.data.type === "ss-calibrate-optics") {
        const nextIn = ev.data.intrinsics as NumMap | undefined;
        const nextDist = ev.data.distortion as NumMap | undefined;
        const locked = lockFocalRef.current;
        if (nextIn) {
          setIntrinsics((prev) => {
            if (locked) {
              return {
                ...prev,
                cx: nextIn.cx ?? prev.cx,
                cy: nextIn.cy ?? prev.cy,
              };
            }
            return { ...prev, ...nextIn };
          });
        }
        if (nextDist && distortionEditable) {
          setDistortion((prev) => ({ ...prev, ...nextDist }));
        }
        setDirty(true);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose, onSaved, toast, distortionEditable]);

  useEffect(() => {
    if (!open || !loaded || !iframeReady) {
      return;
    }
    pushOpticsToIframe(intrinsics, distortion, lockFocal);
  }, [
    open,
    loaded,
    iframeReady,
    intrinsics,
    distortion,
    lockFocal,
    pushOpticsToIframe,
  ]);

  useEffect(() => {
    const recompute = () => setAutoLayout(chooseAutoPanelLayout());
    recompute();
    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, []);

  const setCalLayoutMode = useCallback((mode: PanelLayoutMode) => {
    setLayoutMode(mode);
    writePanelLayoutMode(mode);
  }, []);

  const resolvedLayout: PanelLayout =
    layoutMode === "auto" ? autoLayout : layoutMode;

  const setFocal = (key: "fx" | "fy", value: string) => {
    if (lockFocal) {
      return;
    }
    setIntrinsics((prev) => ({ ...prev, [key]: value }));
    markDirty();
  };

  const setDistort = (key: string, value: string) => {
    if (!distortionEditable) {
      return;
    }
    setDistortion((prev) => ({ ...prev, [key]: value }));
    markDirty();
  };

  const setResolution = (dim: "width" | "height", value: string) => {
    const nextW = dim === "width" ? value : width;
    const nextH = dim === "height" ? value : height;
    if (dim === "width") {
      setWidth(value);
    } else {
      setHeight(value);
    }
    const w = parseNum(nextW);
    const h = parseNum(nextH);
    setIntrinsics((prev) => ({
      ...prev,
      cx: w !== undefined ? String(w / 2) : prev.cx,
      cy: h !== undefined ? String(h / 2) : prev.cy,
    }));
    markDirty();
  };

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    const payload: Record<string, unknown> = {
      name: name.trim(),
      sensor_id: sensorIdEdit.trim() || sensorId,
      scene: sceneId,
      intrinsics: {
        fx: parseNum(intrinsics.fx) ?? 0,
        fy: parseNum(intrinsics.fy) ?? 0,
        cx: parseNum(intrinsics.cx) ?? 0,
        cy: parseNum(intrinsics.cy) ?? 0,
      },
      distortion: {
        k1: parseNum(distortion.k1) ?? 0,
        k2: parseNum(distortion.k2) ?? 0,
        p1: parseNum(distortion.p1) ?? 0,
        p2: parseNum(distortion.p2) ?? 0,
        k3: parseNum(distortion.k3) ?? 0,
      },
    };
    const w = parseNum(width);
    const h = parseNum(height);
    if (w !== undefined && h !== undefined) {
      payload.resolution = { width: w, height: h };
    }
    if (hasAdvanced) {
      payload.cv_subsystem = cvSubsystem;
      payload.undistort = undistort;
      payload.modelconfig = modelconfig.trim() || null;
      payload.use_camera_pipeline = useCameraPipeline;
    }
    try {
      iframeRef.current?.contentWindow?.postMessage(
        { type: "ss-calibrate-save-points" },
        window.location.origin,
      );
      await api.updateCamera(authToken, sensorId, payload);
      toast.show("Camera saved", "ok");
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
      id="ss-cam-calibrate-form"
      className="ss-workspace-panel-form"
      onSubmit={submit}
    >
      {error ? <p className="ss-workspace-panel-error">{error}</p> : null}
      {busy && !loaded ? (
        <p className="ss-workspace-panel-hint">Loading camera…</p>
      ) : null}

      <FormSection
        id="ss-cam-cal-identity"
        title="Identity"
        description="Camera name and pipeline id."
      >
        <TextField
          id="ss-cam-cal-name"
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
          id="ss-cam-cal-sensor-id"
          label="Camera ID"
          value={sensorIdEdit}
          onChange={(ev) => {
            setSensorIdEdit(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
        <TextField
          id="ss-cam-cal-scene"
          label="Scene"
          value={sceneId}
          readOnly
          disabled
        />
      </FormSection>

      <FormSection
        id="ss-cam-cal-intrinsics"
        title="Intrinsics"
        description="Lock fx and fy when focal length is known so calibration treats them as constraints. Unlock to estimate them (6+ point pairs). cx and cy follow resolution."
        className="ss-form-section--columns"
      >
        <div className="ss-cal-focal-lock">
          <input
            type="checkbox"
            id="ss-cam-cal-lock-focal"
            checked={lockFocal}
            disabled={busy}
            onChange={(ev) => {
              setLockFocal(ev.target.checked);
              markDirty();
            }}
          />
          <label htmlFor="ss-cam-cal-lock-focal">
            Lock fx &amp; fy (known intrinsics)
          </label>
        </div>
        <TextField
          id="ss-cam-cal-fx"
          label="fx"
          inputMode="decimal"
          value={intrinsics.fx}
          onChange={(ev) => setFocal("fx", ev.target.value)}
          disabled={busy || lockFocal}
          readOnly={lockFocal}
          title={
            lockFocal
              ? "Unlock fx & fy to edit or estimate focal length"
              : "Focal length x"
          }
        />
        <TextField
          id="ss-cam-cal-fy"
          label="fy"
          inputMode="decimal"
          value={intrinsics.fy}
          onChange={(ev) => setFocal("fy", ev.target.value)}
          disabled={busy || lockFocal}
          readOnly={lockFocal}
          title={
            lockFocal
              ? "Unlock fx & fy to edit or estimate focal length"
              : "Focal length y"
          }
        />
        <TextField
          id="ss-cam-cal-cx"
          label="cx"
          inputMode="decimal"
          value={intrinsics.cx}
          readOnly
          disabled
          title="Principal point x (derived from frame width)"
        />
        <TextField
          id="ss-cam-cal-cy"
          label="cy"
          inputMode="decimal"
          value={intrinsics.cy}
          readOnly
          disabled
          title="Principal point y (derived from frame height)"
        />
      </FormSection>

      <FormSection
        id="ss-cam-cal-distortion"
        title="Distortion"
        description={
          distortionEditable
            ? "Radial and tangential coefficients."
            : "Distortion is read-only on Docker deploys (matches Manager form)."
        }
        className="ss-form-section--columns"
      >
        {(["k1", "k2", "p1", "p2", "k3"] as const).map((key) => (
          <TextField
            key={key}
            id={`ss-cam-cal-d-${key}`}
            label={key}
            inputMode="decimal"
            value={distortion[key]}
            onChange={(ev) => setDistort(key, ev.target.value)}
            disabled={busy || !distortionEditable}
            readOnly={!distortionEditable}
          />
        ))}
      </FormSection>

      <FormSection
        id="ss-cam-cal-resolution"
        title="Resolution"
        description="Frame size in pixels. Changing size updates cx/cy to the image center."
        className="ss-form-section--columns"
      >
        <TextField
          id="ss-cam-cal-width"
          label="Width"
          inputMode="numeric"
          value={width}
          onChange={(ev) => setResolution("width", ev.target.value)}
          disabled={busy}
        />
        <TextField
          id="ss-cam-cal-height"
          label="Height"
          inputMode="numeric"
          value={height}
          onChange={(ev) => setResolution("height", ev.target.value)}
          disabled={busy}
        />
      </FormSection>

      {hasAdvanced ? (
        <FormSection
          id="ss-cam-cal-advanced"
          title="Advanced"
          description="Pipeline and decode options (Kubernetes only)."
          collapsible
          defaultOpen={false}
        >
          <SelectField
            id="ss-cam-cal-cv"
            label="Decode device"
            value={cvSubsystem}
            onChange={(ev) => {
              setCvSubsystem(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          >
            <option value="AUTO">AUTO</option>
            <option value="GPU">GPU</option>
            <option value="CPU">CPU</option>
          </SelectField>
          <SelectField
            id="ss-cam-cal-undistort"
            label="Undistort"
            value={undistort ? "true" : "false"}
            onChange={(ev) => {
              setUndistort(ev.target.value === "true");
              markDirty();
            }}
            disabled
            title="Undistort is disabled until DLSPS supports cameraundistort"
          >
            <option value="false">No</option>
            <option value="true">Yes</option>
          </SelectField>
          <TextField
            id="ss-cam-cal-modelconfig"
            label="Model config"
            value={modelconfig}
            onChange={(ev) => {
              setModelconfig(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <SelectField
            id="ss-cam-cal-pipeline"
            label="Use camera pipeline"
            value={useCameraPipeline ? "true" : "false"}
            onChange={(ev) => {
              setUseCameraPipeline(ev.target.value === "true");
              markDirty();
            }}
            disabled={busy}
          >
            <option value="false">No</option>
            <option value="true">Yes</option>
          </SelectField>
        </FormSection>
      ) : null}
    </form>
  );

  return (
    <WorkspacePanel
      open={open}
      title="Calibrate camera"
      layout="bleed"
      dirty={dirty}
      leaveTitle="Leave calibration?"
      leaveBody="You may have unsaved calibration changes. Leave without saving?"
      onClose={onClose}
      actions={
        <>
          <PanelLayoutToggle
            layoutMode={layoutMode}
            onChange={setCalLayoutMode}
          />
          <Button
            variant="primary"
            disabled={busy || !loaded || !dirty}
            form="ss-cam-calibrate-form"
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
            <h3 className="ss-form-section-title">Point correspondence</h3>
            <p className="ss-workspace-panel-hint" style={{ marginBottom: 0 }}>
              Place matching points on the camera frame and scene map. With fx/fy
              unlocked and 6+ pairs, focal length can be estimated into the
              settings panel.
            </p>
          </div>
          {cameraPk ? (
            <div className="ss-workspace-cal-preview-frame">
              <iframe
                ref={iframeRef}
                title="Point calibrator"
                src={`/cam/calibrate/${cameraPk}?embed=1`}
                onLoad={() => setIframeReady(true)}
              />
            </div>
          ) : (
            <p className="ss-workspace-panel-hint">
              Camera primary key is missing; point calibrator cannot load.
            </p>
          )}
        </div>
        <aside className="ss-cal-workspace-aside">{formBody}</aside>
      </div>
    </WorkspacePanel>
  );
}
