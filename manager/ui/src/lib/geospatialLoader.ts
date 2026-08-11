// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

const SCRIPT_IDS = [
  "ss-geo-map-interface",
  "ss-geo-google-plugin",
  "ss-geo-mapbox-plugin",
  "ss-geo-geomanager",
] as const;

const SCRIPT_SRCS = [
  "/static/js/geospatial/map-interface.js",
  "/static/js/geospatial/google-maps-plugin.js",
  "/static/js/geospatial/mapbox-plugin.js",
  "/static/js/geospatial/geomanager.js",
] as const;

function loadScript(id: string, src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id) as HTMLScriptElement | null;
    if (existing) {
      if (existing.dataset.loaded === "1") {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error(`Failed to load ${src}`)),
        { once: true },
      );
      return;
    }
    const script = document.createElement("script");
    script.id = id;
    script.src = src;
    script.async = false;
    script.onload = () => {
      script.dataset.loaded = "1";
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

/** Load Mapbox/Google geospatial plugins once (order matters). */
export async function loadGeospatialScripts(): Promise<void> {
  for (let i = 0; i < SCRIPT_SRCS.length; i += 1) {
    await loadScript(SCRIPT_IDS[i], SCRIPT_SRCS[i]);
  }
}

export type GeospatialApplyResult = {
  scale: string;
  mapCornersLla: string;
  outputLla: "true" | "false";
  mapCenterLat: string;
  mapCenterLng: string;
  mapZoom: string;
  mapBearing: string;
  geospatialProvider: string;
  mapFilename: string;
  mapMediaUrl: string;
};

declare global {
  interface Window {
    GeoManager?: new () => {
      initialize: (config: Record<string, unknown>) => Promise<void>;
      setMapProvider: (
        provider: string,
        config?: Record<string, unknown>,
      ) => Promise<void>;
      moveToLocation: () => void;
      generateBounds: () => void;
      getCurrentMapInstance: () => unknown;
      getMapStrategy: () => {
        getCenter?: () => { lat: () => number; lng: () => number } | {
          lat: number;
          lng: number;
        };
        getZoom?: () => number;
        getBearing?: () => number;
        map?: {
          getCenter?: () =>
            | { lat: number; lng: number }
            | { lat: () => number; lng: () => number };
          getZoom?: () => number;
          getBearing?: () => number;
        };
      } | null;
    };
    mapManager?: InstanceType<NonNullable<Window["GeoManager"]>>;
    saveCurrentMapSettings?: () => void;
  }
}
