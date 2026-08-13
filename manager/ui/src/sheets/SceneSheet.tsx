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
import { checkMappingServiceAvailable } from "../lib/meshGeneration";
import {
  appendGeospatialSceneFields,
  fetchGeospatialMapFile,
} from "../lib/geospatialSceneForm";
import {
  GeospatialMapPicker,
} from "./GeospatialMapPicker";
import type { GeospatialApplyResult } from "../lib/geospatialLoader";

type Props = {
  open: boolean;
  mode: "create" | "edit";
  sceneUid?: string | null;
  authToken: string;
  onClose: () => void;
  onSaved: (sceneUid?: string, opts?: { setup?: "reconstruct" }) => void;
};

type MapSource = "upload" | "reconstruct" | "geospatial";

const MAPPING_ENABLE_HINT =
  "Mapping is not running. Upload a map, use geospatial, or start mapping with: docker compose --profile mapping up -d";

export function SceneSheet({
  open,
  mode,
  sceneUid,
  authToken,
  onClose,
  onSaved,
}: Props) {
  const toast = useAppToast();
  const [name, setName] = useState("");
  const [scale, setScale] = useState("100");
  const [mapFile, setMapFile] = useState<File | null>(null);
  const [mapSource, setMapSource] = useState<MapSource>("upload");
  const [mappingAvailable, setMappingAvailable] = useState(false);
  const [mappingChecked, setMappingChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [outputLla, setOutputLla] = useState<"true" | "false">("false");
  const [mapCornersLla, setMapCornersLla] = useState("");
  const [geospatialProvider, setGeospatialProvider] = useState("google");
  const [mapZoom, setMapZoom] = useState("15");
  const [mapCenterLat, setMapCenterLat] = useState("");
  const [mapCenterLng, setMapCenterLng] = useState("");
  const [mapBearing, setMapBearing] = useState("0");
  const [geoResult, setGeoResult] = useState<GeospatialApplyResult | null>(
    null,
  );
  const [mapSnapshotName, setMapSnapshotName] = useState<string | null>(null);
  const [geoPickerOpen, setGeoPickerOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setMapFile(null);
    setGeoResult(null);
    setMapSnapshotName(null);
    setOutputLla("false");
    setMapCornersLla("");
    setGeospatialProvider("google");
    setMapZoom("15");
    setMapCenterLat("");
    setMapCenterLng("");
    setMapBearing("0");
    if (mode === "create") {
      setName("");
      setScale("100");
      setMappingChecked(false);
      let cancelled = false;
      checkMappingServiceAvailable(authToken).then((ok) => {
        if (cancelled) {
          return;
        }
        setMappingAvailable(ok);
        setMappingChecked(true);
        setMapSource(ok ? "reconstruct" : "upload");
      });
      return () => {
        cancelled = true;
      };
    }
    if (!sceneUid) {
      return;
    }
    let cancelled = false;
    setBusy(true);
    api
      .getScene(authToken, sceneUid)
      .then((s) => {
        if (cancelled) {
          return;
        }
        setName(String(s.name || ""));
        setScale(s.scale != null ? String(s.scale) : "100");
      })
      .catch((e: RestError) => {
        if (!cancelled) {
          setError(e.message || "Failed to load scene");
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
  }, [open, mode, sceneUid, authToken]);

  const applyGeospatialForCreate = async (result: GeospatialApplyResult) => {
    setBusy(true);
    setError(null);
    try {
      const file = await fetchGeospatialMapFile(result);
      setGeoResult(result);
      setMapFile(file);
      setScale(result.scale || scale);
      setMapCornersLla(result.mapCornersLla);
      setOutputLla(result.outputLla);
      setGeospatialProvider(result.geospatialProvider);
      setMapZoom(result.mapZoom);
      setMapCenterLat(result.mapCenterLat);
      setMapCenterLng(result.mapCenterLng);
      setMapBearing(result.mapBearing);
      setMapSnapshotName(result.mapFilename);
      toast.show("Basemap positioned — create the scene to save", "ok");
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to apply geospatial map";
      setError(msg);
      throw new Error(msg);
    } finally {
      setBusy(false);
    }
  };

  const createDisabled =
    busy ||
    (mode === "create" &&
      ((mapSource === "upload" && !mapFile) ||
        (mapSource === "geospatial" && !geoResult) ||
        (mapSource === "reconstruct" &&
          (!mappingChecked || !mappingAvailable))));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") {
        if (mapSource === "upload" && !mapFile) {
          setError("Choose a map file to upload");
          return;
        }
        if (mapSource === "geospatial" && (!geoResult || !mapFile)) {
          setError("Position a geospatial basemap before creating the scene");
          return;
        }
        if (mapSource === "reconstruct" && !mappingAvailable) {
          setError(
            "Mapping service is not available. Upload a map or use geospatial instead.",
          );
          return;
        }

        const form = new FormData();
        form.append("name", name.trim());
        if (mapSource === "geospatial" && geoResult && mapFile) {
          appendGeospatialSceneFields(form, geoResult, {
            mapFile,
          });
        } else {
          form.append("map_type", "map_upload");
          if (scale.trim()) {
            form.append("scale", scale.trim());
          }
          if (mapSource === "upload" && mapFile) {
            form.append("map", mapFile);
          }
        }

        const created = (await api.createScene(authToken, form)) as {
          uid?: string;
        };
        toast.show("Scene created", "ok");
        onSaved(
          created?.uid,
          mapSource === "reconstruct" ? { setup: "reconstruct" } : undefined,
        );
      } else if (sceneUid) {
        const form = new FormData();
        form.append("name", name.trim());
        if (scale.trim()) {
          form.append("scale", scale.trim());
        }
        if (mapFile) {
          form.append("map", mapFile);
        }
        await api.updateScene(authToken, sceneUid, form);
        toast.show("Scene updated", "ok");
        onSaved(sceneUid);
      }
      onClose();
    } catch (err) {
      setError((err as RestError).message || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Drawer
        open={open}
        title={mode === "create" ? "New scene" : "Edit scene"}
        onClose={onClose}
        wide
        actions={
          <Button
            variant="primary"
            disabled={createDisabled}
            form="ss-scene-sheet-form"
            type="submit"
          >
            {busy ? "Saving…" : mode === "create" ? "Create scene" : "Save"}
          </Button>
        }
      >
        <form
          id="ss-scene-sheet-form"
          className="ss-drawer-form"
          onSubmit={submit}
        >
          {error ? <p className="ss-drawer-error">{error}</p> : null}
          <FormSection
            id="ss-scene-identity"
            title="Identity"
            description="How this scene appears in the gallery."
          >
            <TextField
              id="ss-scene-name"
              label="Name"
              value={name}
              onChange={(ev) => setName(ev.target.value)}
              required
              disabled={busy}
            />
          </FormSection>

          {mode === "create" ? (
            <FormSection
              id="ss-scene-map-source"
              title="Map source"
              description="Choose how this scene gets its floor plan. Tracking needs a map and calibrated cameras."
            >
              <fieldset className="ss-map-source-fieldset">
                <legend className="ss-text-field-label">How will you provide the map?</legend>
                <label className="ss-map-source-option">
                  <input
                    type="radio"
                    name="ss-map-source"
                    value="reconstruct"
                    checked={mapSource === "reconstruct"}
                    disabled={busy || (mappingChecked && !mappingAvailable)}
                    onChange={() => setMapSource("reconstruct")}
                  />
                  <span>
                    Reconstruct from cameras
                    {mappingChecked && !mappingAvailable
                      ? " (mapping unavailable)"
                      : ""}
                  </span>
                </label>
                <label className="ss-map-source-option">
                  <input
                    type="radio"
                    name="ss-map-source"
                    value="upload"
                    checked={mapSource === "upload"}
                    disabled={busy}
                    onChange={() => setMapSource("upload")}
                  />
                  <span>Upload map (image / GLB)</span>
                </label>
                <label className="ss-map-source-option">
                  <input
                    type="radio"
                    name="ss-map-source"
                    value="geospatial"
                    checked={mapSource === "geospatial"}
                    disabled={busy}
                    onChange={() => setMapSource("geospatial")}
                  />
                  <span>Geospatial map</span>
                </label>
              </fieldset>
              {mappingChecked && !mappingAvailable ? (
                <p className="ss-drawer-hint">{MAPPING_ENABLE_HINT}</p>
              ) : null}
            </FormSection>
          ) : null}

          {mode === "edit" || mapSource === "upload" ? (
            <FormSection
              id="ss-scene-map"
              title="Map"
              description={
                mode === "create"
                  ? "Floor plan image or 3D mesh for this scene."
                  : "Floor plan and scale."
              }
            >
              <TextField
                id="ss-scene-scale"
                label="Scale (px per meter)"
                value={scale}
                onChange={(ev) => setScale(ev.target.value)}
                disabled={busy}
              />
              <div className="ss-text-field">
                <label className="ss-text-field-label" htmlFor="ss-scene-map">
                  Map file
                </label>
                <div className="ss-text-field-control">
                  <input
                    id="ss-scene-map"
                    type="file"
                    accept="image/*,.pdf,.svg,.glb,.gltf"
                    disabled={busy}
                    onChange={(ev) =>
                      setMapFile(ev.target.files?.[0] || null)
                    }
                    required={mode === "create" && mapSource === "upload"}
                  />
                </div>
              </div>
            </FormSection>
          ) : null}

          {mode === "create" && mapSource === "reconstruct" ? (
            <FormSection
              id="ss-scene-reconstruct"
              title="Reconstruction"
              description="Create an empty scene, add cameras, then generate a mesh on the scene page."
            >
              <p className="ss-drawer-hint">
                No map file is needed now. After create, add cameras that cover
                the space, then use Generate Mesh on the scene map. Scale is set
                from the reconstruction.
              </p>
            </FormSection>
          ) : null}

          {mode === "create" && mapSource === "geospatial" ? (
            <>
              <FormSection
                id="ss-scene-geo-map"
                title="Geospatial basemap"
                description="Frame the scene on the map, then create. Advanced fields stay under settings."
              >
                <div className="ss-text-field ss-form-section--span-2">
                  <span className="ss-text-field-label">Basemap</span>
                  <div
                    className="ss-text-field-control"
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                      alignItems: "center",
                    }}
                  >
                    <Button
                      type="button"
                      variant="primary"
                      disabled={busy}
                      onClick={() => setGeoPickerOpen(true)}
                    >
                      Position map
                    </Button>
                    <span className="ss-workspace-panel-hint" style={{ margin: 0 }}>
                      {mapSnapshotName
                        ? `Positioned: ${mapSnapshotName}`
                        : "Open a floating map view to frame the scene"}
                    </span>
                  </div>
                </div>
              </FormSection>
              <FormSection
                id="ss-scene-geo-settings"
                title="Geospatial settings"
                description="Provider, scale, and WGS84 corners (filled when you position the map)."
                collapsible
                defaultOpen={false}
                className="ss-form-section--columns"
              >
                <TextField
                  id="ss-scene-geo-scale"
                  label="Scale (px per meter)"
                  value={scale}
                  onChange={(ev) => setScale(ev.target.value)}
                  disabled={busy}
                />
                <SelectField
                  id="ss-scene-output-lla"
                  label="Output geospatial coordinates"
                  value={outputLla}
                  onChange={(ev) =>
                    setOutputLla(ev.target.value === "true" ? "true" : "false")
                  }
                  disabled={busy}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </SelectField>
                <SelectField
                  id="ss-scene-geo-provider"
                  label="Geospatial provider"
                  value={geospatialProvider}
                  onChange={(ev) => setGeospatialProvider(ev.target.value)}
                  disabled={busy}
                >
                  <option value="google">Google Maps</option>
                  <option value="mapbox">Mapbox</option>
                </SelectField>
                <TextField
                  id="ss-scene-map-zoom"
                  label="Map zoom"
                  value={mapZoom}
                  onChange={(ev) => setMapZoom(ev.target.value)}
                  disabled={busy}
                />
                <TextField
                  id="ss-scene-map-lat"
                  label="Map center latitude"
                  value={mapCenterLat}
                  onChange={(ev) => setMapCenterLat(ev.target.value)}
                  disabled={busy}
                />
                <TextField
                  id="ss-scene-map-lng"
                  label="Map center longitude"
                  value={mapCenterLng}
                  onChange={(ev) => setMapCenterLng(ev.target.value)}
                  disabled={busy}
                />
                <TextField
                  id="ss-scene-map-bearing"
                  label="Map bearing (degrees)"
                  value={mapBearing}
                  onChange={(ev) => setMapBearing(ev.target.value)}
                  disabled={busy}
                />
                <div className="ss-text-field ss-form-section--span-2">
                  <label
                    className="ss-text-field-label"
                    htmlFor="ss-scene-corners"
                  >
                    Map corners LLA (JSON)
                  </label>
                  <div className="ss-text-field-control">
                    <textarea
                      id="ss-scene-corners"
                      className="form-control ss-text-field-input"
                      rows={4}
                      value={mapCornersLla}
                      disabled={busy}
                      onChange={(ev) => setMapCornersLla(ev.target.value)}
                    />
                  </div>
                </div>
              </FormSection>
            </>
          ) : null}
        </form>
      </Drawer>
      {mode === "create" ? (
        <GeospatialMapPicker
          open={geoPickerOpen}
          provider={geospatialProvider}
          mapZoom={mapZoom}
          mapCenterLat={mapCenterLat}
          mapCenterLng={mapCenterLng}
          mapBearing={mapBearing}
          onClose={() => setGeoPickerOpen(false)}
          onApply={applyGeospatialForCreate}
        />
      ) : null}
    </>
  );
}
