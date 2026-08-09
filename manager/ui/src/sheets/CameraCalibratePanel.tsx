// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { WorkspacePanel } from "../components/WorkspacePanel";
import { FormSection } from "../components/FormSection";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";
import "./CameraCalibratePanel.css";

type Props = {
  open: boolean;
  /** Django DB pk as string (from bootstrap cameras[].id) */
  cameraPk: string;
  /** sensor_id for REST (from bootstrap cameras[].sensorId) */
  sensorId: string;
  sceneId: string;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

type NumMap = Record<string, string>;
type CalLayoutMode = "auto" | "stack" | "row";
type CalLayout = "stack" | "row";

const CAL_LAYOUT_KEY = "ss-calibrate-layout-mode";

const LAYOUT_OPTIONS: {
  mode: CalLayoutMode;
  label: string;
  title: string;
  icon: string;
}[] = [
  {
    mode: "auto",
    label: "Auto",
    title: "Automatic layout from viewport size",
    icon: "bi-magic",
  },
  {
    mode: "stack",
    label: "Below",
    title: "Settings below point picking (watch intrinsics while calibrating)",
    icon: "bi-distribute-vertical",
  },
  {
    mode: "row",
    label: "Side",
    title: "Settings beside point picking",
    icon: "bi-layout-sidebar-reverse",
  },
];

function readCalLayoutMode(): CalLayoutMode {
  try {
    const raw = window.localStorage.getItem(CAL_LAYOUT_KEY);
    if (raw === "auto" || raw === "stack" || raw === "row") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return "auto";
}

function chooseAutoCalLayout(): CalLayout {
  return window.innerWidth >= 1200 ? "row" : "stack";
}

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
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [layoutMode, setLayoutMode] = useState<CalLayoutMode>(() =>
    typeof window !== "undefined" ? readCalLayoutMode() : "auto",
  );
  const [autoLayout, setAutoLayout] = useState<CalLayout>(() =>
    typeof window !== "undefined" ? chooseAutoCalLayout() : "stack",
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
  const [width, setWidth] = useState("");
  const [height, setHeight] = useState("");
  const [cvSubsystem, setCvSubsystem] = useState("AUTO");
  const [undistort, setUndistort] = useState(false);
  const [modelconfig, setModelconfig] = useState("model_config.json");
  const [useCameraPipeline, setUseCameraPipeline] = useState(false);
  const [hasAdvanced, setHasAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const markDirty = useCallback(() => {
    if (loaded) {
      setDirty(true);
    }
  }, [loaded]);

  useEffect(() => {
    if (!open || !sensorId) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);
    setDirty(false);
    setLoaded(false);
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
        const advancedPresent =
          "cv_subsystem" in cam ||
          "undistort" in cam ||
          "modelconfig" in cam ||
          "use_camera_pipeline" in cam;
        setHasAdvanced(advancedPresent);
        setCvSubsystem(String(cam.cv_subsystem || "AUTO"));
        setUndistort(Boolean(cam.undistort));
        setModelconfig(String(cam.modelconfig || "model_config.json"));
        setUseCameraPipeline(Boolean(cam.use_camera_pipeline));
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
  }, [open, sensorId, authToken]);

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
        if (nextIn) {
          setIntrinsics((prev) => ({ ...prev, ...nextIn }));
        }
        if (nextDist) {
          setDistortion((prev) => ({ ...prev, ...nextDist }));
        }
        setDirty(true);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [open, onClose, onSaved, toast]);

  useEffect(() => {
    const recompute = () => setAutoLayout(chooseAutoCalLayout());
    recompute();
    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, []);

  const setCalLayoutMode = useCallback((mode: CalLayoutMode) => {
    setLayoutMode(mode);
    try {
      window.localStorage.setItem(CAL_LAYOUT_KEY, mode);
    } catch {
      /* ignore */
    }
  }, []);

  const resolvedLayout: CalLayout =
    layoutMode === "auto" ? autoLayout : layoutMode;

  const setIntrinsic = (key: string, value: string) => {
    setIntrinsics((prev) => ({ ...prev, [key]: value }));
    markDirty();
  };

  const setDistort = (key: string, value: string) => {
    setDistortion((prev) => ({ ...prev, [key]: value }));
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
        description="Focal length and principal point."
        className="ss-form-section--columns"
      >
        {(["fx", "fy", "cx", "cy"] as const).map((key) => (
          <TextField
            key={key}
            id={`ss-cam-cal-${key}`}
            label={key}
            inputMode="decimal"
            value={intrinsics[key]}
            onChange={(ev) => setIntrinsic(key, ev.target.value)}
            disabled={busy}
          />
        ))}
      </FormSection>

      <FormSection
        id="ss-cam-cal-distortion"
        title="Distortion"
        description="Radial and tangential coefficients."
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
            disabled={busy}
          />
        ))}
      </FormSection>

      <FormSection
        id="ss-cam-cal-resolution"
        title="Resolution"
        description="Frame size in pixels."
        className="ss-form-section--columns"
      >
        <TextField
          id="ss-cam-cal-width"
          label="Width"
          inputMode="numeric"
          value={width}
          onChange={(ev) => {
            setWidth(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
        <TextField
          id="ss-cam-cal-height"
          label="Height"
          inputMode="numeric"
          value={height}
          onChange={(ev) => {
            setHeight(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
      </FormSection>

      {hasAdvanced ? (
        <FormSection
          id="ss-cam-cal-advanced"
          title="Advanced"
          description="Pipeline and decode options."
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
            disabled={busy}
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
          <div
            className="ss-layout-toggle ss-cal-layout-toggle"
            role="group"
            aria-label="Calibration panel layout"
          >
            {LAYOUT_OPTIONS.map((opt) => {
              const active = layoutMode === opt.mode;
              const hint =
                opt.mode === "auto" ? ` (now ${autoLayout})` : "";
              return (
                <button
                  key={opt.mode}
                  type="button"
                  className={`ss-layout-toggle-btn${active ? " is-active" : ""}`}
                  title={`${opt.title}${hint}`}
                  aria-pressed={active}
                  onClick={() => setCalLayoutMode(opt.mode)}
                >
                  <i className={`bi ${opt.icon}`} aria-hidden="true" />
                  <span className="ss-layout-toggle-label">{opt.label}</span>
                </button>
              );
            })}
          </div>
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
              Place matching points on the camera frame and scene map. Intrinsics
              update in the settings panel as calibration runs.
            </p>
          </div>
          {cameraPk ? (
            <div className="ss-workspace-cal-preview-frame">
              <iframe
                ref={iframeRef}
                title="Point calibrator"
                src={`/cam/calibrate/${cameraPk}?embed=1`}
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
