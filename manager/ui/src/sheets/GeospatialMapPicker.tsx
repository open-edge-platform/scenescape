// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { SelectField } from "../components/SelectField";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  loadGeospatialScripts,
  type GeospatialApplyResult,
} from "../lib/geospatialLoader";
import "./GeospatialMapPicker.css";

const GEO_MAP_ID = "ss-geo-map";

export type GeospatialMapPickerProps = {
  open: boolean;
  provider: string;
  mapZoom: string;
  mapCenterLat: string;
  mapCenterLng: string;
  mapBearing: string;
  onClose: () => void;
  onApply: (result: GeospatialApplyResult) => void | Promise<void>;
};

function coord(v: unknown): number | null {
  if (typeof v === "function") {
    const n = Number((v as () => number)());
    return Number.isFinite(n) ? n : null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function centerParts(center: unknown): { lat: string; lng: string } {
  if (!center || typeof center !== "object") {
    return { lat: "", lng: "" };
  }
  const c = center as { lat?: unknown; lng?: unknown };
  const lat = coord(c.lat);
  const lng = coord(c.lng);
  return {
    lat: lat != null ? String(lat) : "",
    lng: lng != null ? String(lng) : "",
  };
}

function scaleFromView(lat: number, zoom: number): string {
  const earth = 40075016.686;
  const pixelsPerDegree = (256 * Math.pow(2, zoom)) / 360;
  const metersPerDegreeLng =
    (earth / 360) * Math.cos((lat * Math.PI) / 180);
  return (pixelsPerDegree / metersPerDegreeLng).toFixed(2);
}

function cornersFromBounds(bounds: unknown): string | null {
  if (!bounds || typeof bounds !== "object") {
    return null;
  }
  const b = bounds as {
    getNorthEast?: () => { lat?: unknown; lng?: unknown };
    getSouthWest?: () => { lat?: unknown; lng?: unknown };
  };
  const ne = b.getNorthEast?.();
  const sw = b.getSouthWest?.();
  if (!ne || !sw) {
    return null;
  }
  const neLat = coord(ne.lat);
  const neLng = coord(ne.lng);
  const swLat = coord(sw.lat);
  const swLng = coord(sw.lng);
  if (neLat == null || neLng == null || swLat == null || swLng == null) {
    return null;
  }
  return JSON.stringify([
    [swLat, swLng, 0],
    [neLat, swLng, 0],
    [neLat, neLng, 0],
    [swLat, neLng, 0],
  ]);
}

function readLiveMap(): {
  corners: string | null;
  lat: string;
  lng: string;
  zoom: string;
  bearing: string;
  scale: string;
} {
  const empty = {
    corners: null,
    lat: "",
    lng: "",
    zoom: "",
    bearing: "",
    scale: "",
  };
  const map = window.mapManager?.getCurrentMapInstance?.() as
    | {
        getBounds?: () => unknown;
        getCenter?: () => unknown;
        getZoom?: () => number;
        getBearing?: () => number;
        resize?: () => void;
      }
    | null
    | undefined;
  if (!map?.getBounds || !map.getCenter || !map.getZoom) {
    return empty;
  }
  map.resize?.();
  const parts = centerParts(map.getCenter());
  const zoomN = Number(map.getZoom());
  const bearingN =
    typeof map.getBearing === "function" ? Number(map.getBearing()) : 0;
  const latN = Number(parts.lat);
  return {
    corners: cornersFromBounds(map.getBounds()),
    lat: parts.lat,
    lng: parts.lng,
    zoom: Number.isFinite(zoomN) ? String(zoomN) : "",
    bearing: Number.isFinite(bearingN) ? String(bearingN) : "0",
    scale:
      Number.isFinite(latN) && Number.isFinite(zoomN)
        ? scaleFromView(latN, zoomN)
        : "",
  };
}

function waitForSnapshot(timeoutMs = 60000): {
  promise: Promise<{ filename: string; mediaUrl: string }>;
  abort: () => void;
} {
  let timer = 0;
  let onEvent: ((ev: Event) => void) | null = null;
  const abort = () => {
    if (timer) {
      window.clearTimeout(timer);
      timer = 0;
    }
    if (onEvent) {
      window.removeEventListener("ss-geospatial-snapshot", onEvent);
      onEvent = null;
    }
  };
  const promise = new Promise<{ filename: string; mediaUrl: string }>(
    (resolve, reject) => {
      timer = window.setTimeout(() => {
        abort();
        reject(new Error("Timed out waiting for map snapshot"));
      }, timeoutMs);
      onEvent = (ev: Event) => {
        const detail = (ev as CustomEvent).detail as {
          success?: boolean;
          filename?: string;
          mediaUrl?: string;
          error?: string;
        };
        abort();
        if (detail?.success && detail.filename) {
          resolve({
            filename: detail.filename,
            mediaUrl: detail.mediaUrl || `/media/${detail.filename}`,
          });
          return;
        }
        reject(new Error(detail?.error || "Failed to save map snapshot"));
      };
      window.addEventListener("ss-geospatial-snapshot", onEvent);
    },
  );
  return { promise, abort };
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  if (err && typeof err === "object" && "message" in err) {
    const msg = (err as { message?: unknown }).message;
    if (typeof msg === "string" && msg.trim()) {
      return msg;
    }
  }
  return fallback;
}

/**
 * Hovering geospatial map picker — Mapbox/Google position → bounds + snapshot.
 */
export function GeospatialMapPicker({
  open,
  provider: initialProvider,
  mapZoom,
  mapCenterLat,
  mapCenterLng,
  mapBearing,
  onClose,
  onApply,
}: GeospatialMapPickerProps) {
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState(initialProvider || "google");
  const [location, setLocation] = useState("");
  const initRef = useRef(false);

  useEffect(() => {
    if (open) {
      setProvider(initialProvider || "google");
      setDirty(false);
      setConfirmClose(false);
      setError(null);
      setReady(false);
      initRef.current = false;
    }
  }, [open, initialProvider]);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    const boot = async () => {
      try {
        await loadGeospatialScripts();
        if (cancelled) {
          return;
        }
        if (!window.GeoManager) {
          throw new Error("Geospatial map manager failed to load");
        }
        if (!window.mapManager) {
          window.mapManager = new window.GeoManager();
        }
        window.saveCurrentMapSettings = () => {
          const live = readLiveMap();
          const latEl = document.getElementById(
            "id_map_center_lat",
          ) as HTMLInputElement | null;
          const lngEl = document.getElementById(
            "id_map_center_lng",
          ) as HTMLInputElement | null;
          const zoomEl = document.getElementById(
            "id_map_zoom",
          ) as HTMLInputElement | null;
          const bearingEl = document.getElementById(
            "id_map_bearing",
          ) as HTMLInputElement | null;
          const cornersEl = document.getElementById(
            "id_map_corners_lla",
          ) as HTMLInputElement | null;
          const scaleEl = document.getElementById(
            "id_scale",
          ) as HTMLInputElement | null;
          if (latEl && live.lat) {
            latEl.value = live.lat;
          }
          if (lngEl && live.lng) {
            lngEl.value = live.lng;
          }
          if (zoomEl && live.zoom) {
            zoomEl.value = live.zoom;
          }
          if (bearingEl && live.bearing) {
            bearingEl.value = live.bearing;
          }
          if (cornersEl && live.corners) {
            cornersEl.value = live.corners;
          }
          if (scaleEl && live.scale) {
            scaleEl.value = live.scale;
          }
        };
        const lat = Number(mapCenterLat);
        const lng = Number(mapCenterLng);
        const zoom = Number(mapZoom);
        const bearing = Number(mapBearing);
        await window.mapManager.initialize({
          containerId: GEO_MAP_ID,
          provider: initialProvider || "google",
          lat: Number.isFinite(lat) ? lat : 37.7749,
          lng: Number.isFinite(lng) ? lng : -122.4194,
          zoom: Number.isFinite(zoom) && zoom > 0 ? zoom : 15,
          rotation: Number.isFinite(bearing) ? bearing : 0,
        });
        window.requestAnimationFrame(() => {
          const map = window.mapManager?.getCurrentMapInstance?.() as
            | { resize?: () => void }
            | undefined;
          map?.resize?.();
        });
        if (!cancelled) {
          setReady(true);
          initRef.current = true;
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to open map");
          setReady(false);
        }
      }
    };
    const t = window.setTimeout(() => {
      void boot();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
      const mapEl = document.getElementById(GEO_MAP_ID);
      if (mapEl) {
        mapEl.innerHTML = "";
      }
    };
    // Init once per open from the props at open-time; provider switches use setMapProvider.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional open-only boot
  }, [open]);

  const requestClose = () => {
    if (dirty) {
      setConfirmClose(true);
      return;
    }
    onClose();
  };

  const onProviderChange = async (next: string) => {
    setProvider(next);
    setDirty(true);
    setError(null);
    const providerField = document.getElementById(
      "id_geospatial_provider",
    ) as HTMLInputElement | null;
    if (providerField) {
      providerField.value = next;
    }
    try {
      if (!window.mapManager) {
        return;
      }
      const lat = Number(mapCenterLat);
      const lng = Number(mapCenterLng);
      const zoom = Number(mapZoom);
      const bearing = Number(mapBearing);
      await window.mapManager.setMapProvider(next, {
        containerId: GEO_MAP_ID,
        lat: Number.isFinite(lat) ? lat : 37.7749,
        lng: Number.isFinite(lng) ? lng : -122.4194,
        zoom: Number.isFinite(zoom) && zoom > 0 ? zoom : 15,
        rotation: Number.isFinite(bearing) ? bearing : 0,
      });
      window.requestAnimationFrame(() => {
        const map = window.mapManager?.getCurrentMapInstance?.() as
          | { resize?: () => void }
          | undefined;
        map?.resize?.();
      });
      setReady(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to switch provider");
      setReady(false);
    }
  };

  const searchLocation = () => {
    setDirty(true);
    window.mapManager?.moveToLocation();
  };

  const finish = useCallback(async () => {
    if (!window.mapManager) {
      setError("Map is not ready");
      return;
    }
    setBusy(true);
    setError(null);
    const pending = waitForSnapshot();
    try {
      const live = readLiveMap();
      if (!live.corners) {
        throw new Error("Map corners were not generated");
      }
      const cornersEl = document.getElementById(
        "id_map_corners_lla",
      ) as HTMLInputElement | null;
      const scaleEl = document.getElementById(
        "id_scale",
      ) as HTMLInputElement | null;
      const outputEl = document.getElementById(
        "id_output_lla",
      ) as HTMLInputElement | null;
      if (cornersEl) {
        cornersEl.value = live.corners;
      }
      if (scaleEl && live.scale) {
        scaleEl.value = live.scale;
      }
      if (outputEl) {
        outputEl.value = "true";
      }

      window.mapManager.generateBounds();
      const snap = await pending.promise;
      const after = readLiveMap();
      const corners = after.corners || live.corners;

      await onApply({
        scale: after.scale || live.scale || "100",
        mapCornersLla: corners,
        outputLla: "true",
        mapCenterLat: after.lat || live.lat,
        mapCenterLng: after.lng || live.lng,
        mapZoom: after.zoom || live.zoom || mapZoom || "15",
        mapBearing: after.bearing || live.bearing || mapBearing || "0",
        geospatialProvider: provider,
        mapFilename: snap.filename,
        mapMediaUrl: snap.mediaUrl,
      });
      setDirty(false);
      onClose();
    } catch (e) {
      pending.abort();
      setError(errorMessage(e, "Failed to save map position"));
    } finally {
      setBusy(false);
    }
  }, [onApply, onClose, provider, mapZoom, mapBearing]);

  if (!open) {
    return null;
  }

  return createPortal(
    <>
      <div className="ss-geo-modal" role="presentation" onClick={requestClose}>
        <div
          className="ss-geo-modal-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="ss-geo-modal-header">
            <h2 className="ss-geo-modal-title" id={titleId}>
              Position geospatial map
            </h2>
            <div className="ss-geo-modal-actions">
              <Button variant="secondary" type="button" onClick={requestClose}>
                Cancel
              </Button>
              <Button
                variant="primary"
                type="button"
                disabled={busy || !ready}
                onClick={() => void finish()}
              >
                {busy ? "Saving…" : "Done"}
              </Button>
            </div>
          </div>
          <div className="ss-geo-picker">
            <div className="ss-geo-picker-toolbar">
              <SelectField
                id="mapProvider"
                label="Provider"
                value={provider}
                onChange={(ev) => void onProviderChange(ev.target.value)}
                disabled={busy}
              >
                <option value="google">Google Maps</option>
                <option value="mapbox">Mapbox</option>
              </SelectField>
              <TextField
                id="locationInput"
                label="Find location"
                value={location}
                onChange={(ev) => {
                  setLocation(ev.target.value);
                  setDirty(true);
                }}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter") {
                    ev.preventDefault();
                    searchLocation();
                  }
                }}
                disabled={busy || !ready}
              />
              <Button
                variant="secondary"
                type="button"
                disabled={busy || !ready || !location.trim()}
                onClick={searchLocation}
              >
                Go
              </Button>
              <p className="ss-geo-picker-hint">
                Pan, zoom, and rotate the map to frame the scene. Done captures
                a snapshot and WGS84 corners, then saves them to the scene.
              </p>
              {error ? <p className="ss-geo-picker-error">{error}</p> : null}
            </div>
            <div className="ss-geo-picker-map-wrap">
              <div id={GEO_MAP_ID} />
            </div>
            <div
              id="ss-geo-map-bridge"
              className="ss-geo-picker-bridge"
              aria-hidden
            >
              <input
                type="hidden"
                id="id_map_type"
                value="geospatial_map"
                readOnly
              />
              <input
                type="hidden"
                id="id_geospatial_provider"
                value={provider}
                readOnly
              />
              <input type="hidden" id="id_scale" defaultValue="" />
              <input type="hidden" id="id_map_corners_lla" defaultValue="" />
              <input type="hidden" id="id_output_lla" defaultValue="" />
              <input
                type="hidden"
                id="id_map_center_lat"
                defaultValue={mapCenterLat}
              />
              <input
                type="hidden"
                id="id_map_center_lng"
                defaultValue={mapCenterLng}
              />
              <input type="hidden" id="id_map_zoom" defaultValue={mapZoom} />
              <input
                type="hidden"
                id="id_map_bearing"
                defaultValue={mapBearing}
              />
              <input type="file" id="id_map" style={{ display: "none" }} />
            </div>
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={confirmClose}
        title="Leave without applying?"
        confirmLabel="Leave"
        cancelLabel="Stay"
        danger
        onConfirm={() => {
          setConfirmClose(false);
          onClose();
        }}
        onCancel={() => setConfirmClose(false)}
      >
        <p>Map position will not be saved to the scene. Leave without applying?</p>
      </ConfirmDialog>
    </>,
    document.body,
  );
}
