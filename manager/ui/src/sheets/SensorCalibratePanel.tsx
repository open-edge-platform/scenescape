// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
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
import { WorkspaceSplitter } from "../scene/WorkspaceSplitter";
import {
  CAL_PANEL_SIZE_KEY,
  useWorkspaceDensity,
} from "../scene/useWorkspaceDensity";
import "./CameraCalibratePanel.css";
import "../components/PanelLayoutToggle.css";

type Props = {
  open: boolean;
  sensorPk: string;
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

type AreaMode = "scene" | "circle" | "poly";

function numStr(v: unknown, fallback = ""): string {
  if (v == null || v === "") {
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

function sectorsFromSensor(s: Record<string, unknown>): {
  green: string;
  yellow: string;
  red: string;
  max: string;
} {
  const cr = s.color_ranges;
  if (cr && typeof cr === "object") {
    const obj = cr as { sectors?: { color: string; color_min: number }[]; range_max?: number };
    const sectors = obj.sectors || [];
    const min = (color: string, fb: number) => {
      const hit = sectors.find((x) => x.color === color);
      return hit != null ? String(hit.color_min) : String(fb);
    };
    return {
      green: min("green", 0),
      yellow: min("yellow", 2),
      red: min("red", 5),
      max: obj.range_max != null ? String(obj.range_max) : "10",
    };
  }
  return { green: "0", yellow: "2", red: "5", max: "10" };
}

/**
 * Full-viewport sensor calibrate panel — identity + area via REST (no iframe).
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
  const [name, setName] = useState("");
  const [sensorIdEdit, setSensorIdEdit] = useState(sensorId);
  const [singletonType, setSingletonType] = useState("environmental");
  const [area, setArea] = useState<AreaMode>("scene");
  const [centerX, setCenterX] = useState("0");
  const [centerY, setCenterY] = useState("0");
  const [radius, setRadius] = useState("1");
  const [pointsText, setPointsText] = useState("[]");
  const [greenMin, setGreenMin] = useState("0");
  const [yellowMin, setYellowMin] = useState("2");
  const [redMin, setRedMin] = useState("5");
  const [rangeMax, setRangeMax] = useState("10");
  const [mapUrl, setMapUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [layoutMode, setLayoutMode] = useState<PanelLayoutMode>(() =>
    typeof window !== "undefined" ? readPanelLayoutMode() : "auto",
  );
  const [autoLayout, setAutoLayout] = useState<PanelLayout>(() =>
    typeof window !== "undefined" ? chooseAutoPanelLayout() : "stack",
  );

  const resolvedLayout: PanelLayout =
    layoutMode === "auto" ? autoLayout : layoutMode;
  const { panelSizePx, setPanelSizePx } = useWorkspaceDensity(resolvedLayout, {
    storageKey: CAL_PANEL_SIZE_KEY,
    enableFocus: false,
  });
  const restUid = sensorIdEdit.trim() || sensorId;

  const setPanelLayoutMode = useCallback((mode: PanelLayoutMode) => {
    setLayoutMode(mode);
    writePanelLayoutMode(mode);
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
    setLoaded(false);
    Promise.all([
      api.getSensor(authToken, sensorId),
      api.getScene(authToken, sceneId).catch(() => null),
    ])
      .then(([s, scene]) => {
        if (cancelled) {
          return;
        }
        setName(String(s.name || ""));
        setSensorIdEdit(String(s.sensor_id || s.uid || sensorId));
        setSingletonType(String(s.singleton_type || "environmental"));
        const areaMode = (String(s.area || "scene") as AreaMode) || "scene";
        setArea(
          areaMode === "circle" || areaMode === "poly" ? areaMode : "scene",
        );
        const center = Array.isArray(s.center) ? s.center : [0, 0];
        setCenterX(numStr(center[0], "0"));
        setCenterY(numStr(center[1], "0"));
        setRadius(s.radius != null ? numStr(s.radius, "1") : "1");
        setPointsText(
          Array.isArray(s.points) ? JSON.stringify(s.points, null, 2) : "[]",
        );
        const secs = sectorsFromSensor(s);
        setGreenMin(secs.green);
        setYellowMin(secs.yellow);
        setRedMin(secs.red);
        setRangeMax(secs.max);
        const map =
          scene && typeof scene === "object"
            ? (scene as { map?: unknown; map_url?: unknown }).map ||
              (scene as { map_url?: unknown }).map_url
            : null;
        setMapUrl(typeof map === "string" && map ? map : null);
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
  }, [open, sensorId, sceneId, authToken]);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!restUid) {
      setError("Sensor id is missing");
      return;
    }
    setBusy(true);
    setError(null);
    const payload: Record<string, unknown> = {
      name: name.trim(),
      sensor_id: restUid,
      scene: sceneId,
      singleton_type: singletonType,
      area,
      color_ranges: {
        sectors: [
          { color: "green", color_min: parseNum(greenMin) ?? 0 },
          { color: "yellow", color_min: parseNum(yellowMin) ?? 2 },
          { color: "red", color_min: parseNum(redMin) ?? 5 },
        ],
        range_max: parseNum(rangeMax) ?? 10,
      },
    };
    if (area === "circle") {
      const cx = parseNum(centerX);
      const cy = parseNum(centerY);
      const r = parseNum(radius);
      if (cx === undefined || cy === undefined || r === undefined) {
        setError("Circle area requires center X/Y and radius");
        setBusy(false);
        return;
      }
      payload.center = [cx, cy];
      payload.radius = r;
    }
    if (area === "poly") {
      try {
        const pts = JSON.parse(pointsText) as unknown;
        if (!Array.isArray(pts)) {
          throw new SyntaxError("points must be an array");
        }
        payload.points = pts;
      } catch {
        setError("Polygon points must be valid JSON [[x,y], …]");
        setBusy(false);
        return;
      }
    }
    try {
      await api.updateSensor(authToken, restUid, payload);
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
      <FormSection title="Identity" description="Sensor name and pipeline id.">
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
      <FormSection
        title="Area"
        description="Coverage on the scene map (REST-backed)."
      >
        <SelectField
          id="ss-sensor-cal-area"
          label="Area type"
          value={area}
          onChange={(ev) => {
            setArea(ev.target.value as AreaMode);
            markDirty();
          }}
          disabled={busy}
        >
          <option value="scene">Entire scene</option>
          <option value="circle">Circle</option>
          <option value="poly">Polygon</option>
        </SelectField>
        {area === "circle" ? (
          <>
            <TextField
              id="ss-sensor-cal-cx"
              label="Center X (m)"
              value={centerX}
              onChange={(ev) => {
                setCenterX(ev.target.value);
                markDirty();
              }}
              disabled={busy}
            />
            <TextField
              id="ss-sensor-cal-cy"
              label="Center Y (m)"
              value={centerY}
              onChange={(ev) => {
                setCenterY(ev.target.value);
                markDirty();
              }}
              disabled={busy}
            />
            <TextField
              id="ss-sensor-cal-r"
              label="Radius (m)"
              value={radius}
              onChange={(ev) => {
                setRadius(ev.target.value);
                markDirty();
              }}
              disabled={busy}
            />
          </>
        ) : null}
        {area === "poly" ? (
          <div className="ss-text-field">
            <label className="ss-text-field-label" htmlFor="ss-sensor-cal-pts">
              Points JSON [[x,y], …]
            </label>
            <div className="ss-text-field-control">
              <textarea
                id="ss-sensor-cal-pts"
                rows={6}
                value={pointsText}
                disabled={busy}
                onChange={(ev) => {
                  setPointsText(ev.target.value);
                  markDirty();
                }}
              />
            </div>
          </div>
        ) : null}
      </FormSection>
      <FormSection
        title="Occupancy colors"
        description="Threshold sectors for scalar visualization."
        className="ss-form-section--columns"
      >
        <TextField
          id="ss-sensor-cal-g"
          label="Green min"
          value={greenMin}
          onChange={(ev) => {
            setGreenMin(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
        <TextField
          id="ss-sensor-cal-y"
          label="Yellow min"
          value={yellowMin}
          onChange={(ev) => {
            setYellowMin(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
        <TextField
          id="ss-sensor-cal-r2"
          label="Red min"
          value={redMin}
          onChange={(ev) => {
            setRedMin(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
        <TextField
          id="ss-sensor-cal-max"
          label="Range max"
          value={rangeMax}
          onChange={(ev) => {
            setRangeMax(ev.target.value);
            markDirty();
          }}
          disabled={busy}
        />
      </FormSection>
    </form>
  );

  return (
    <WorkspacePanel
      open={open && Boolean(sensorPk || sensorId)}
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
        style={{ "--ss-panel-size": `${panelSizePx}px` } as CSSProperties}
      >
        <div className="ss-cal-workspace-main ss-workspace-cal-preview">
          <div className="ss-workspace-cal-preview-meta">
            <h3 className="ss-form-section-title">Area preview</h3>
            <p className="ss-workspace-panel-hint" style={{ marginBottom: 0 }}>
              Area type: <strong>{area}</strong>
              {area === "circle"
                ? ` · center (${centerX}, ${centerY}) · r=${radius}`
                : null}
              {area === "poly" ? " · polygon points in the form" : null}
            </p>
          </div>
          <div className="ss-workspace-cal-preview-frame">
            {mapUrl ? (
              <img
                src={mapUrl}
                alt="Scene map"
                style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
              />
            ) : (
              <p className="ss-workspace-panel-hint">
                Scene map preview unavailable. Edit area fields in the settings
                panel.
              </p>
            )}
          </div>
        </div>
        <WorkspaceSplitter
          layout={resolvedLayout}
          panelSizePx={panelSizePx}
          onResize={setPanelSizePx}
        />
        <aside className="ss-cal-workspace-aside">{formBody}</aside>
      </div>
    </WorkspacePanel>
  );
}
