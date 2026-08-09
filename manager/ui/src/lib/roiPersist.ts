// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { api } from "./rest";

type RoiDraft = {
  title?: string;
  uuid?: string;
  points?: number[][];
  volumetric?: boolean;
  height?: number;
  buffer_size?: number;
  range_max?: number;
  sectors?: { color: string; color_min: number }[];
};

type TripDraft = {
  title?: string;
  uuid?: string;
  points?: number[][];
  height?: number;
};

function isUuid(value: unknown): value is string {
  if (typeof value !== "string" || !value) {
    return false;
  }
  try {
    // Match Django validate_uuid (uuid.UUID(value)).
    const check = value.match(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
    return Boolean(check);
  } catch {
    return false;
  }
}

function listResults(payload: { results?: unknown[] } | unknown[]): unknown[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (payload && Array.isArray(payload.results)) {
    return payload.results;
  }
  return [];
}

function uidOf(row: unknown): string | null {
  if (!row || typeof row !== "object") {
    return null;
  }
  const uid = (row as { uid?: unknown }).uid;
  return typeof uid === "string" && uid ? uid : null;
}

function parseHiddenJson<T>(id: string): T[] {
  const el = document.getElementById(id) as HTMLInputElement | null;
  if (!el?.value) {
    return [];
  }
  try {
    const parsed = JSON.parse(el.value) as unknown;
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function regionPayload(sceneId: string, roi: RoiDraft): Record<string, unknown> {
  const name = (roi.title || "").trim() || `roi_${roi.uuid || "new"}`;
  const payload: Record<string, unknown> = {
    name,
    scene: sceneId,
    points: roi.points || [],
    volumetric: Boolean(roi.volumetric),
    height: typeof roi.height === "number" ? roi.height : 1,
    buffer_size: typeof roi.buffer_size === "number" ? roi.buffer_size : 0,
  };
  if (Array.isArray(roi.sectors) && typeof roi.range_max === "number") {
    payload.color_ranges = {
      sectors: roi.sectors,
      range_max: roi.range_max,
    };
  }
  return payload;
}

function tripPayload(sceneId: string, trip: TripDraft): Record<string, unknown> {
  const name = (trip.title || "").trim() || `tripwire_${trip.uuid || "new"}`;
  return {
    name,
    scene: sceneId,
    points: trip.points || [],
    ...(typeof trip.height === "number" ? { height: trip.height } : {}),
  };
}

/**
 * Bulk-sync ROI / tripwire geometry from SVG stringify outputs via REST.
 * Mirrors Django saveRegionData / saveTripwireData (upsert + delete orphans).
 */
export async function persistSceneGeometry(
  authToken: string,
  sceneId: string,
): Promise<void> {
  window.stringifyRois?.();
  window.stringifyTripwires?.();

  const rois = parseHiddenJson<RoiDraft>("id_rois");
  const trips = parseHiddenJson<TripDraft>("tripwires");

  const [existingRegions, existingTrips] = await Promise.all([
    api.getRegions(authToken, sceneId).then(listResults),
    api.getTripwires(authToken, sceneId).then(listResults),
  ]);

  const existingRegionIds = new Set(
    existingRegions.map(uidOf).filter((u): u is string => Boolean(u)),
  );
  const keepRegion = new Set<string>();
  for (const roi of rois) {
    const payload = regionPayload(sceneId, roi);
    if (isUuid(roi.uuid) && existingRegionIds.has(roi.uuid)) {
      await api.updateRegion(authToken, roi.uuid, payload);
      keepRegion.add(roi.uuid);
    } else {
      const created = await api.createRegion(authToken, payload);
      const uid = uidOf(created);
      if (uid) {
        keepRegion.add(uid);
      }
    }
  }

  for (const uid of existingRegionIds) {
    if (!keepRegion.has(uid)) {
      await api.deleteRegion(authToken, uid);
    }
  }

  const existingTripIds = new Set(
    existingTrips.map(uidOf).filter((u): u is string => Boolean(u)),
  );
  const keepTrip = new Set<string>();
  for (const trip of trips) {
    const payload = tripPayload(sceneId, trip);
    if (isUuid(trip.uuid) && existingTripIds.has(trip.uuid)) {
      await api.updateTripwire(authToken, trip.uuid, payload);
      keepTrip.add(trip.uuid);
    } else {
      const created = await api.createTripwire(authToken, payload);
      const uid = uidOf(created);
      if (uid) {
        keepTrip.add(uid);
      }
    }
  }

  for (const uid of existingTripIds) {
    if (!keepTrip.has(uid)) {
      await api.deleteTripwire(authToken, uid);
    }
  }
}

declare global {
  interface Window {
    stringifyRois?: () => void;
    stringifyTripwires?: () => void;
    ssPersistGeometry?: (
      roiValues?: string[],
    ) => void | Promise<void>;
  }
}
