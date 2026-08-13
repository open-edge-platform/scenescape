// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { GeospatialApplyResult } from "./geospatialLoader";

/** Django/DRF BooleanField+choices only matches str(True)/str(False). */
export function formChoiceBool(value: string | boolean): "True" | "False" {
  return value === true || value === "true" || value === "True"
    ? "True"
    : "False";
}

export async function fetchGeospatialMapFile(
  result: GeospatialApplyResult,
): Promise<File> {
  const snapRes = await fetch(result.mapMediaUrl, {
    credentials: "same-origin",
  });
  if (!snapRes.ok) {
    throw new Error("Could not download generated map snapshot");
  }
  const blob = await snapRes.blob();
  return new File([blob], result.mapFilename || "geospatial_map.png", {
    type: blob.type || "image/png",
  });
}

/** Append geospatial fields and map snapshot for scene create/update FormData. */
export function appendGeospatialSceneFields(
  form: FormData,
  result: GeospatialApplyResult,
  opts?: { name?: string; mapFile?: File },
): void {
  if (opts?.name != null) {
    form.append("name", opts.name);
  }
  form.append("map_type", "geospatial_map");
  form.append("scale", result.scale || "100");
  form.append("output_lla", formChoiceBool(true));
  form.append("map_corners_lla", result.mapCornersLla);
  form.append("geospatial_provider", result.geospatialProvider);
  if (result.mapZoom) {
    form.append("map_zoom", result.mapZoom);
  }
  if (result.mapCenterLat) {
    form.append("map_center_lat", result.mapCenterLat);
  }
  if (result.mapCenterLng) {
    form.append("map_center_lng", result.mapCenterLng);
  }
  if (result.mapBearing) {
    form.append("map_bearing", result.mapBearing);
  }
  if (opts?.mapFile) {
    form.append("map", opts.mapFile);
  }
}
