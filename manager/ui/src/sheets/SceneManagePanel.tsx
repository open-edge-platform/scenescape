// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { WorkspacePanel } from "../components/WorkspacePanel";
import { FormSection } from "../components/FormSection";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { Button } from "../components/Button";
import { FormShell } from "../components/FormShell";
import { api, type RestError } from "../lib/rest";
import { useAppToast } from "../components/ToastProvider";

type Props = {
  open: boolean;
  sceneId: string;
  authToken: string;
  onClose: () => void;
  onSaved: () => void;
};

type Vec3 = [string, string, string];

const FORM_ID = "ss-scene-manage-form";

const CALIBRATION_OPTIONS = [
  { value: "Manual", label: "Manual" },
  { value: "AprilTag", label: "AprilTag" },
  { value: "Markerless", label: "Markerless" },
];

function str(v: unknown, fallback = ""): string {
  if (v == null) {
    return fallback;
  }
  return String(v);
}

function boolStr(v: unknown, fallback: "true" | "false"): "true" | "false" {
  if (v === true || v === "true" || v === "True") {
    return "true";
  }
  if (v === false || v === "false" || v === "False") {
    return "false";
  }
  return fallback;
}

function vec3From(
  arr: unknown,
  fallback: [number, number, number],
  flat?: { x?: unknown; y?: unknown; z?: unknown },
): Vec3 {
  if (Array.isArray(arr) && arr.length >= 3) {
    return [str(arr[0], String(fallback[0])), str(arr[1], String(fallback[1])), str(arr[2], String(fallback[2]))];
  }
  if (flat) {
    return [
      str(flat.x, String(fallback[0])),
      str(flat.y, String(fallback[1])),
      str(flat.z, String(fallback[2])),
    ];
  }
  return [String(fallback[0]), String(fallback[1]), String(fallback[2])];
}

function parseVec3(v: Vec3): [number, number, number] {
  return [Number(v[0]) || 0, Number(v[1]) || 0, Number(v[2]) || 0];
}

function cornersToText(v: unknown): string {
  if (v == null) {
    return "";
  }
  if (typeof v === "string") {
    return v;
  }
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return "";
  }
}

function parseCorners(text: string): unknown | null {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }
  return JSON.parse(trimmed) as unknown;
}

export function SceneManagePanel({
  open,
  sceneId,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [mapType, setMapType] = useState("map_upload");
  const [scale, setScale] = useState("100");
  const [mapFile, setMapFile] = useState<File | null>(null);

  const [useTracker, setUseTracker] = useState<"true" | "false">("true");
  const [regulatedRate, setRegulatedRate] = useState("30");
  const [externalUpdateRate, setExternalUpdateRate] = useState("30");

  const [outputLla, setOutputLla] = useState<"true" | "false">("false");
  const [mapCornersLla, setMapCornersLla] = useState("");
  const [geospatialProvider, setGeospatialProvider] = useState("google");
  const [mapZoom, setMapZoom] = useState("15");
  const [mapCenterLat, setMapCenterLat] = useState("");
  const [mapCenterLng, setMapCenterLng] = useState("");
  const [mapBearing, setMapBearing] = useState("0");

  const [meshTranslation, setMeshTranslation] = useState<Vec3>(["0", "0", "0"]);
  const [meshRotation, setMeshRotation] = useState<Vec3>(["0", "0", "0"]);
  const [meshScale, setMeshScale] = useState<Vec3>(["1", "1", "1"]);

  const [cameraCalibration, setCameraCalibration] = useState("Manual");
  const [apriltagSize, setApriltagSize] = useState("0.162");
  const [numberOfLocalizations, setNumberOfLocalizations] = useState("50");
  const [globalFeature, setGlobalFeature] = useState("netvlad");
  const [minimumNumberOfMatches, setMinimumNumberOfMatches] = useState("20");
  const [inlierThreshold, setInlierThreshold] = useState("0.5");

  const markDirty = () => setDirty(true);

  const poseNonDefault =
    meshTranslation.join(",") !== "0,0,0" ||
    meshRotation.join(",") !== "0,0,0" ||
    meshScale.join(",") !== "1,1,1";
  const geoRelevant =
    mapType === "geospatial_map" ||
    outputLla === "true" ||
    Boolean(mapCornersLla.trim()) ||
    Boolean(mapCenterLat.trim()) ||
    Boolean(mapCenterLng.trim());
  const geoError =
    Boolean(error) &&
    /corner|lla|geo|map.?center|bearing|provider/i.test(error || "");
  const poseError =
    Boolean(error) && /translation|rotation|mesh|pose|scale_[xyz]/i.test(error || "");
  const autoCalError =
    Boolean(error) &&
    /calibration|apriltag|localization|feature|inlier|match/i.test(error || "");

  const sectionKey = loading ? "loading" : "ready";

  useEffect(() => {
    if (!open || !sceneId) {
      return;
    }
    let cancelled = false;
    setError(null);
    setDirty(false);
    setMapFile(null);
    setLoading(true);
    setBusy(true);
    api
      .getScene(authToken, sceneId)
      .then((s) => {
        if (cancelled) {
          return;
        }
        setName(str(s.name));
        setMapType(str(s.map_type, "map_upload"));
        setScale(s.scale != null ? str(s.scale) : "100");
        setUseTracker(boolStr(s.use_tracker, "true"));
        setRegulatedRate(s.regulated_rate != null ? str(s.regulated_rate) : "30");
        setExternalUpdateRate(
          s.external_update_rate != null ? str(s.external_update_rate) : "30",
        );
        setOutputLla(boolStr(s.output_lla, "false"));
        setMapCornersLla(cornersToText(s.map_corners_lla));
        setGeospatialProvider(str(s.geospatial_provider, "google"));
        setMapZoom(s.map_zoom != null ? str(s.map_zoom) : "15");
        setMapCenterLat(s.map_center_lat != null ? str(s.map_center_lat) : "");
        setMapCenterLng(s.map_center_lng != null ? str(s.map_center_lng) : "");
        setMapBearing(s.map_bearing != null ? str(s.map_bearing) : "0");
        setMeshTranslation(
          vec3From(s.mesh_translation, [0, 0, 0], {
            x: s.translation_x,
            y: s.translation_y,
            z: s.translation_z,
          }),
        );
        setMeshRotation(
          vec3From(s.mesh_rotation, [0, 0, 0], {
            x: s.rotation_x,
            y: s.rotation_y,
            z: s.rotation_z,
          }),
        );
        setMeshScale(
          vec3From(s.mesh_scale, [1, 1, 1], {
            x: s.scale_x,
            y: s.scale_y,
            z: s.scale_z,
          }),
        );
        setCameraCalibration(str(s.camera_calibration, "Manual"));
        setApriltagSize(s.apriltag_size != null ? str(s.apriltag_size) : "0.162");
        setNumberOfLocalizations(
          s.number_of_localizations != null
            ? str(s.number_of_localizations)
            : "50",
        );
        setGlobalFeature(str(s.global_feature, "netvlad"));
        setMinimumNumberOfMatches(
          s.minimum_number_of_matches != null
            ? str(s.minimum_number_of_matches)
            : "20",
        );
        setInlierThreshold(
          s.inlier_threshold != null ? str(s.inlier_threshold) : "0.5",
        );
        setDirty(false);
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load scene");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, sceneId, authToken]);

  const setVec =
    (setter: (v: Vec3) => void, current: Vec3, index: 0 | 1 | 2) =>
    (ev: ChangeEvent<HTMLInputElement>) => {
      const next: Vec3 = [...current];
      next[index] = ev.target.value;
      setter(next);
      markDirty();
    };

  const buildJsonBody = (): Record<string, unknown> => {
    const body: Record<string, unknown> = {
      name: name.trim(),
      map_type: mapType,
      scale: scale.trim() ? Number(scale) : null,
      use_tracker: useTracker === "true",
      regulated_rate: regulatedRate.trim() ? Number(regulatedRate) : null,
      external_update_rate: externalUpdateRate.trim()
        ? Number(externalUpdateRate)
        : null,
      output_lla: outputLla === "true",
      geospatial_provider: geospatialProvider,
      map_zoom: mapZoom.trim() ? Number(mapZoom) : null,
      map_bearing: mapBearing.trim() ? Number(mapBearing) : null,
      mesh_translation: parseVec3(meshTranslation),
      mesh_rotation: parseVec3(meshRotation),
      mesh_scale: parseVec3(meshScale),
      camera_calibration: cameraCalibration,
      apriltag_size: apriltagSize.trim() ? Number(apriltagSize) : null,
      number_of_localizations: numberOfLocalizations.trim()
        ? Number(numberOfLocalizations)
        : null,
      global_feature: globalFeature.trim(),
      minimum_number_of_matches: minimumNumberOfMatches.trim()
        ? Number(minimumNumberOfMatches)
        : null,
      inlier_threshold: inlierThreshold.trim() ? Number(inlierThreshold) : null,
    };
    if (mapCenterLat.trim()) {
      body.map_center_lat = Number(mapCenterLat);
    }
    if (mapCenterLng.trim()) {
      body.map_center_lng = Number(mapCenterLng);
    }
    const corners = mapCornersLla.trim()
      ? parseCorners(mapCornersLla)
      : null;
    if (corners != null) {
      body.map_corners_lla = corners;
    }
    return body;
  };

  const buildFormData = (): FormData => {
    const form = new FormData();
    form.append("name", name.trim());
    form.append("map_type", mapType);
    if (scale.trim()) {
      form.append("scale", scale.trim());
    }
    form.append("use_tracker", useTracker);
    if (regulatedRate.trim()) {
      form.append("regulated_rate", regulatedRate.trim());
    }
    if (externalUpdateRate.trim()) {
      form.append("external_update_rate", externalUpdateRate.trim());
    }
    form.append("output_lla", outputLla);
    if (mapCornersLla.trim()) {
      form.append("map_corners_lla", mapCornersLla.trim());
    }
    form.append("geospatial_provider", geospatialProvider);
    if (mapZoom.trim()) {
      form.append("map_zoom", mapZoom.trim());
    }
    if (mapCenterLat.trim()) {
      form.append("map_center_lat", mapCenterLat.trim());
    }
    if (mapCenterLng.trim()) {
      form.append("map_center_lng", mapCenterLng.trim());
    }
    if (mapBearing.trim()) {
      form.append("map_bearing", mapBearing.trim());
    }
    form.append("camera_calibration", cameraCalibration);
    if (apriltagSize.trim()) {
      form.append("apriltag_size", apriltagSize.trim());
    }
    if (numberOfLocalizations.trim()) {
      form.append("number_of_localizations", numberOfLocalizations.trim());
    }
    form.append("global_feature", globalFeature.trim());
    if (minimumNumberOfMatches.trim()) {
      form.append("minimum_number_of_matches", minimumNumberOfMatches.trim());
    }
    if (inlierThreshold.trim()) {
      form.append("inlier_threshold", inlierThreshold.trim());
    }
    if (mapFile) {
      form.append("map", mapFile);
    }
    return form;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mapCornersLla.trim()) {
        parseCorners(mapCornersLla);
      }
      if (mapFile) {
        await api.updateScene(authToken, sceneId, buildFormData());
        // mesh_* lists only work over JSON; apply pose after multipart map upload
        await api.updateSceneJson(authToken, sceneId, {
          name: name.trim(),
          mesh_translation: parseVec3(meshTranslation),
          mesh_rotation: parseVec3(meshRotation),
          mesh_scale: parseVec3(meshScale),
        });
      } else {
        await api.updateSceneJson(authToken, sceneId, buildJsonBody());
      }
      toast.show("Scene saved", "ok");
      setDirty(false);
      onSaved();
      onClose();
    } catch (err) {
      const re = err as RestError & { message?: string };
      if (err instanceof SyntaxError) {
        setError("map_corners_lla must be valid JSON");
      } else {
        setError(re.message || "Save failed");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <WorkspacePanel
      open={open}
      title="Manage Scene"
      layout="form"
      dirty={dirty}
      onClose={onClose}
      actions={
        <Button
          variant="primary"
          type="submit"
          form={FORM_ID}
          disabled={busy || loading || !dirty}
          title={dirty ? "Save changes" : "No unsaved changes"}
          className={dirty ? "ss-btn--dirty" : undefined}
        >
          {busy && !loading ? "Saving…" : dirty ? "Save" : "Saved"}
        </Button>
      }
    >
      <FormShell
        id={FORM_ID}
        className="ss-workspace-panel-form ss-workspace-panel-form--bleed"
        error={error}
        hint={loading ? "Loading scene…" : null}
        busy={busy || loading}
        onSubmit={submit}
      >

        <FormSection
          id="ss-scene-manage-identity"
          title="Identity"
          description="How this scene appears in the gallery and navigation."
        >
          <TextField
            id="ss-scene-manage-name"
            label="Name"
            value={name}
            onChange={(ev) => {
              setName(ev.target.value);
              markDirty();
            }}
            required
            disabled={busy}
          />
        </FormSection>

        <FormSection
          id="ss-scene-manage-map"
          title="Map"
          description="Floor plan image or geospatial basemap and scene scale."
        >
          <SelectField
            id="ss-scene-manage-map-type"
            label="Map type"
            value={mapType}
            onChange={(ev) => {
              setMapType(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          >
            <option value="map_upload">Upload Map</option>
            <option value="geospatial_map">Geospatial Map</option>
          </SelectField>
          <TextField
            id="ss-scene-manage-scale"
            label="Scale (px per meter)"
            value={scale}
            onChange={(ev) => {
              setScale(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <div className="ss-text-field">
            <label
              className="ss-text-field-label"
              htmlFor="ss-scene-manage-map-file"
            >
              Map file
            </label>
            <div className="ss-text-field-control">
              <input
                id="ss-scene-manage-map-file"
                type="file"
                accept="image/*,.pdf,.svg,.glb,.gltf,.ply,.zip,video/*"
                disabled={busy}
                onChange={(ev) => {
                  setMapFile(ev.target.files?.[0] || null);
                  markDirty();
                }}
              />
            </div>
          </div>
        </FormSection>

        <FormSection
          id="ss-scene-manage-tracking"
          title="Tracking"
          description="How often scene detections and external updates are published."
        >
          <SelectField
            id="ss-scene-manage-use-tracker"
            label="Use tracker"
            value={useTracker}
            onChange={(ev) => {
              setUseTracker(ev.target.value === "true" ? "true" : "false");
              markDirty();
            }}
            disabled={busy}
          >
            <option value="true">Yes</option>
            <option value="false">No</option>
          </SelectField>
          <TextField
            id="ss-scene-manage-regulated-rate"
            label="Regulate rate (Hz)"
            value={regulatedRate}
            onChange={(ev) => {
              setRegulatedRate(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-external-rate"
            label="Max external update rate (Hz)"
            value={externalUpdateRate}
            onChange={(ev) => {
              setExternalUpdateRate(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
        </FormSection>

        <FormSection
          key={`geo-${sectionKey}-${mapType}`}
          id="ss-scene-manage-geo"
          title="Geospatial settings"
          description="WGS84 corners and LLA output for Mapbox / Google Maps scenes."
          collapsible
          defaultOpen={!loading && geoRelevant}
          forceOpen={geoError}
          className="ss-form-section--columns"
        >
          <SelectField
            id="ss-scene-manage-output-lla"
            label="Output geospatial coordinates"
            value={outputLla}
            onChange={(ev) => {
              setOutputLla(ev.target.value === "true" ? "true" : "false");
              markDirty();
            }}
            disabled={busy}
          >
            <option value="true">Yes</option>
            <option value="false">No</option>
          </SelectField>
          <div className="ss-text-field ss-form-section--span-2">
            <label
              className="ss-text-field-label"
              htmlFor="ss-scene-manage-corners"
            >
              Map corners LLA (JSON)
            </label>
            <div className="ss-text-field-control">
              <textarea
                id="ss-scene-manage-corners"
                className="form-control ss-text-field-input"
                rows={6}
                value={mapCornersLla}
                disabled={busy}
                onChange={(ev) => {
                  setMapCornersLla(ev.target.value);
                  markDirty();
                }}
              />
            </div>
          </div>
          <SelectField
            id="ss-scene-manage-geo-provider"
            label="Geospatial provider"
            value={geospatialProvider}
            onChange={(ev) => {
              setGeospatialProvider(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          >
            <option value="google">Google Maps</option>
            <option value="mapbox">Mapbox</option>
          </SelectField>
          <TextField
            id="ss-scene-manage-map-zoom"
            label="Map zoom"
            value={mapZoom}
            onChange={(ev) => {
              setMapZoom(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-map-lat"
            label="Map center latitude"
            value={mapCenterLat}
            onChange={(ev) => {
              setMapCenterLat(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-map-lng"
            label="Map center longitude"
            value={mapCenterLng}
            onChange={(ev) => {
              setMapCenterLng(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-map-bearing"
            label="Map bearing (degrees)"
            value={mapBearing}
            onChange={(ev) => {
              setMapBearing(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
        </FormSection>

        <FormSection
          key={`pose-${sectionKey}`}
          id="ss-scene-manage-pose"
          title="Pose"
          description="Translation, rotation, and scale applied to the scene map mesh (.glb)."
          collapsible
          defaultOpen={!loading && poseNonDefault}
          forceOpen={poseError}
          className="ss-form-section--columns"
        >
          <TextField
            id="ss-scene-manage-tx"
            label="Translation X (m)"
            value={meshTranslation[0]}
            onChange={setVec(setMeshTranslation, meshTranslation, 0)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-ty"
            label="Translation Y (m)"
            value={meshTranslation[1]}
            onChange={setVec(setMeshTranslation, meshTranslation, 1)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-tz"
            label="Translation Z (m)"
            value={meshTranslation[2]}
            onChange={setVec(setMeshTranslation, meshTranslation, 2)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-rx"
            label="Rotation X (°)"
            value={meshRotation[0]}
            onChange={setVec(setMeshRotation, meshRotation, 0)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-ry"
            label="Rotation Y (°)"
            value={meshRotation[1]}
            onChange={setVec(setMeshRotation, meshRotation, 1)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-rz"
            label="Rotation Z (°)"
            value={meshRotation[2]}
            onChange={setVec(setMeshRotation, meshRotation, 2)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-sx"
            label="Scale X"
            value={meshScale[0]}
            onChange={setVec(setMeshScale, meshScale, 0)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-sy"
            label="Scale Y"
            value={meshScale[1]}
            onChange={setVec(setMeshScale, meshScale, 1)}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-sz"
            label="Scale Z"
            value={meshScale[2]}
            onChange={setVec(setMeshScale, meshScale, 2)}
            disabled={busy}
          />
        </FormSection>

        <FormSection
          key={`autocal-${sectionKey}`}
          id="ss-scene-manage-autocal"
          title="Auto-calibration"
          description="Feature matching and marker settings for camera auto-calibration."
          collapsible
          defaultOpen={false}
          forceOpen={autoCalError}
        >
          <SelectField
            id="ss-scene-manage-cal-type"
            label="Calibration type"
            value={cameraCalibration}
            onChange={(ev) => {
              setCameraCalibration(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          >
            {CALIBRATION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </SelectField>
          <TextField
            id="ss-scene-manage-apriltag"
            label="AprilTag size (m)"
            value={apriltagSize}
            onChange={(ev) => {
              setApriltagSize(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-localizations"
            label="Number of localizations"
            value={numberOfLocalizations}
            onChange={(ev) => {
              setNumberOfLocalizations(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-global-feature"
            label="Global feature matching"
            value={globalFeature}
            onChange={(ev) => {
              setGlobalFeature(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-min-matches"
            label="Minimum number of matches"
            value={minimumNumberOfMatches}
            onChange={(ev) => {
              setMinimumNumberOfMatches(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
          <TextField
            id="ss-scene-manage-inlier"
            label="Inlier threshold"
            value={inlierThreshold}
            onChange={(ev) => {
              setInlierThreshold(ev.target.value);
              markDirty();
            }}
            disabled={busy}
          />
        </FormSection>
      </FormShell>
    </WorkspacePanel>
  );
}
