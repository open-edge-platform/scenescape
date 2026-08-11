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
import { readMapScale, pixelsToMeters } from "../scene/map/coords";
import { SensorAreaMap } from "./SensorAreaMap";
import "./CameraCalibratePanel.css";
import "../components/PanelLayoutToggle.css";

type Props = {
  open: boolean;
  sensorPk: string;
  sensorId: string;
  sceneId: string;
  authToken: string;
  mapUrlHint?: string | null;
  mapScale?: number | null;
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

function isUnsetCenter(x: unknown, y: unknown): boolean {
  const cx = Number(x);
  const cy = Number(y);
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) {
    return true;
  }
  return Math.abs(cx) < 1e-9 && Math.abs(cy) < 1e-9;
}

/** Scene-map center in meters (matches sscape.js Y flip). */
function mapCenterMeters(
  scale: number,
  mapWidth: number,
  mapHeight: number,
): [number, number] {
  const safeScale = scale > 0 ? scale : 100;
  if (!(mapWidth > 0 && mapHeight > 0)) {
    return [0, 0];
  }
  return pixelsToMeters(mapWidth / 2, mapHeight / 2, safeScale, mapHeight);
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
function parsePointsText(text: string): [number, number][] {
  try {
    const pts = JSON.parse(text) as unknown;
    if (!Array.isArray(pts)) {
      return [];
    }
    return pts
      .filter(
        (p): p is [number, number] =>
          Array.isArray(p) &&
          p.length >= 2 &&
          Number.isFinite(Number(p[0])) &&
          Number.isFinite(Number(p[1])),
      )
      .map((p) => [Number(p[0]), Number(p[1])]);
  } catch {
    return [];
  }
}

export function SensorCalibratePanel({
  open,
  sensorPk,
  sensorId,
  sceneId,
  authToken,
  mapUrlHint = null,
  mapScale = null,
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
  const [mapUrl, setMapUrl] = useState<string | null>(mapUrlHint);
  const [scale, setScale] = useState(() =>
    mapScale && mapScale > 0 ? mapScale : readMapScale(),
  );
  const [mapSize, setMapSize] = useState<{ width: number; height: number } | null>(
    null,
  );
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
        const center = Array.isArray(s.center) ? s.center : null;
        const cx = center ? center[0] : null;
        const cy = center ? center[1] : null;
        const sceneScale =
          scene && typeof scene === "object"
            ? Number((scene as { scale?: unknown }).scale)
            : NaN;
        const resolvedScale =
          Number.isFinite(sceneScale) && sceneScale > 0
            ? sceneScale
            : mapScale && mapScale > 0
              ? mapScale
              : readMapScale();
        setScale(resolvedScale);

        const map =
          scene && typeof scene === "object"
            ? (scene as { map?: unknown; map_url?: unknown }).map ||
              (scene as { map_url?: unknown }).map_url
            : null;
        const fromApi = typeof map === "string" && map ? map : null;
        const resolvedMap = mapUrlHint || fromApi;
        setMapUrl(resolvedMap);

        const applyCenter = (width: number, height: number) => {
          if (isUnsetCenter(cx, cy)) {
            const [mx, my] = mapCenterMeters(resolvedScale, width, height);
            setCenterX(numStr(Number(mx.toFixed(3)), "0"));
            setCenterY(numStr(Number(my.toFixed(3)), "0"));
          } else {
            setCenterX(numStr(cx, "0"));
            setCenterY(numStr(cy, "0"));
          }
        };

        if (resolvedMap) {
          const img = new Image();
          img.onload = () => {
            if (cancelled) {
              return;
            }
            if (img.naturalWidth > 0 && img.naturalHeight > 0) {
              setMapSize({
                width: img.naturalWidth,
                height: img.naturalHeight,
              });
              applyCenter(img.naturalWidth, img.naturalHeight);
            } else if (!isUnsetCenter(cx, cy)) {
              setCenterX(numStr(cx, "0"));
              setCenterY(numStr(cy, "0"));
            }
          };
          img.onerror = () => {
            if (!cancelled && !isUnsetCenter(cx, cy)) {
              setCenterX(numStr(cx, "0"));
              setCenterY(numStr(cy, "0"));
            }
          };
          img.src = resolvedMap;
        } else if (!isUnsetCenter(cx, cy)) {
          setCenterX(numStr(cx, "0"));
          setCenterY(numStr(cy, "0"));
        } else {
          setCenterX("0");
          setCenterY("0");
        }
        setRadius(s.radius != null ? numStr(s.radius, "1") : "1");
        setPointsText(
          Array.isArray(s.points) ? JSON.stringify(s.points, null, 2) : "[]",
        );
        const secs = sectorsFromSensor(s);
        setGreenMin(secs.green);
        setYellowMin(secs.yellow);
        setRedMin(secs.red);
        setRangeMax(secs.max);
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
  }, [open, sensorId, sceneId, authToken, mapUrlHint, mapScale]);

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
        const numeric = pts.filter(
          (p): p is [number, number] =>
            Array.isArray(p) &&
            p.length >= 2 &&
            Number.isFinite(Number(p[0])) &&
            Number.isFinite(Number(p[1])),
        );
        if (numeric.length) {
          const cx =
            numeric.reduce((sum, p) => sum + Number(p[0]), 0) / numeric.length;
          const cy =
            numeric.reduce((sum, p) => sum + Number(p[1]), 0) / numeric.length;
          payload.center = [cx, cy];
        }
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
        description={
          area === "circle"
            ? "Click the map to place the center. Drag the rim to set radius."
            : area === "poly"
              ? "Click the map to add vertices. Click the first point to close."
              : "Coverage on the scene map."
        }
      >
        <SelectField
          id="ss-sensor-cal-area"
          label="Area type"
          value={area}
          onChange={(ev) => {
            const next = ev.target.value as AreaMode;
            setArea(next);
            if (
              next === "circle" &&
              isUnsetCenter(centerX, centerY) &&
              mapSize
            ) {
              const [mx, my] = mapCenterMeters(
                scale,
                mapSize.width,
                mapSize.height,
              );
              setCenterX(String(Number(mx.toFixed(3))));
              setCenterY(String(Number(my.toFixed(3))));
            }
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
              {area === "circle"
                ? "Click the map to place the center. Drag the handle or rim."
                : null}
              {area === "poly"
                ? "Click to add polygon vertices. Click the first point to close."
                : null}
              {area === "scene" ? "Entire scene coverage." : null}
            </p>
          </div>
          <div className="ss-workspace-cal-preview-frame">
            {mapUrl ? (
              <SensorAreaMap
                mapUrl={mapUrl}
                scale={scale}
                area={area}
                centerX={parseNum(centerX) ?? 0}
                centerY={parseNum(centerY) ?? 0}
                radius={parseNum(radius) ?? 1}
                points={parsePointsText(pointsText)}
                onCenterChange={(x, y) => {
                  setCenterX(String(Number(x.toFixed(3))));
                  setCenterY(String(Number(y.toFixed(3))));
                  markDirty();
                }}
                onRadiusChange={(r) => {
                  setRadius(String(Number(r.toFixed(3))));
                  markDirty();
                }}
                onPointsChange={(pts) => {
                  setPointsText(JSON.stringify(pts, null, 2));
                  markDirty();
                }}
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
