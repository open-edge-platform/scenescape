// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Typed ROI / tripwire geometry model for scene detail.
 * React editors own metadata; map owns points. Hidden inputs stay filled
 * for UI-test inject helpers until those helpers call REST directly.
 */

export type GeometryPoint = [number, number];

export type RoiGeometry = {
  uuid: string;
  title: string;
  points: GeometryPoint[];
  volumetric: boolean;
  height: number;
  buffer_size: number;
  range_max: number;
  sectors: { color: string; color_min: number }[];
};

export type TripwireGeometry = {
  uuid: string;
  title: string;
  points: GeometryPoint[];
};

type Listener = () => void;

let rois = new Map<string, RoiGeometry>();
let trips = new Map<string, TripwireGeometry>();
const listeners = new Set<Listener>();

function notify(): void {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      /* ignore */
    }
  });
}

function writeInput(id: string, value: string): void {
  const el = document.getElementById(id) as HTMLInputElement | null;
  if (el) {
    el.value = value;
  }
}

export function subscribeGeometry(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function getRoiList(): RoiGeometry[] {
  return Array.from(rois.values());
}

export function getTripwireList(): TripwireGeometry[] {
  return Array.from(trips.values());
}

export function upsertRoiMeta(
  uuid: string,
  patch: Partial<Omit<RoiGeometry, "uuid" | "points">> & {
    points?: GeometryPoint[];
  },
): void {
  const prev = rois.get(uuid);
  const next: RoiGeometry = {
    uuid,
    title: patch.title ?? prev?.title ?? "",
    points: patch.points ?? prev?.points ?? [],
    volumetric: patch.volumetric ?? prev?.volumetric ?? false,
    height: patch.height ?? prev?.height ?? 1,
    buffer_size: patch.buffer_size ?? prev?.buffer_size ?? 0,
    range_max: patch.range_max ?? prev?.range_max ?? 10,
    sectors: patch.sectors ??
      prev?.sectors ?? [
        { color: "green", color_min: 0 },
        { color: "yellow", color_min: 2 },
        { color: "red", color_min: 5 },
      ],
  };
  rois.set(uuid, next);
  flushGeometryToHidden();
  notify();
}

export function upsertTripMeta(
  uuid: string,
  patch: Partial<Omit<TripwireGeometry, "uuid" | "points">> & {
    points?: GeometryPoint[];
  },
): void {
  const prev = trips.get(uuid);
  const next: TripwireGeometry = {
    uuid,
    title: patch.title ?? prev?.title ?? "",
    points: patch.points ?? prev?.points ?? [],
  };
  trips.set(uuid, next);
  flushGeometryToHidden();
  notify();
}

export function removeRoi(uuid: string): void {
  rois.delete(uuid);
  flushGeometryToHidden();
  notify();
}

export function removeTripwire(uuid: string): void {
  trips.delete(uuid);
  flushGeometryToHidden();
  notify();
}

export function replaceRoiPoints(uuid: string, points: GeometryPoint[]): void {
  const prev = rois.get(uuid);
  if (!prev) {
    rois.set(uuid, {
      uuid,
      title: "",
      points,
      volumetric: false,
      height: 1,
      buffer_size: 0,
      range_max: 10,
      sectors: [
        { color: "green", color_min: 0 },
        { color: "yellow", color_min: 2 },
        { color: "red", color_min: 5 },
      ],
    });
  } else {
    rois.set(uuid, { ...prev, points });
  }
  flushGeometryToHidden();
  notify();
}

export function replaceTripPoints(uuid: string, points: GeometryPoint[]): void {
  const prev = trips.get(uuid);
  if (!prev) {
    trips.set(uuid, { uuid, title: "", points });
  } else {
    trips.set(uuid, { ...prev, points });
  }
  flushGeometryToHidden();
  notify();
}

/** Apply Snap stringify drafts (title + points) into the model without losing sectors. */
export function ingestStringifyRois(
  drafts: Array<{
    uuid?: string;
    title?: string;
    points?: number[][];
    volumetric?: boolean;
    height?: number;
    buffer_size?: number;
    range_max?: number;
    sectors?: { color: string; color_min: number }[];
  }>,
): void {
  const keep = new Set<string>();
  for (const d of drafts) {
    const uuid = String(d.uuid || "").trim();
    if (!uuid) {
      continue;
    }
    keep.add(uuid);
    const points = (d.points || []).map(
      (p) => [Number(p[0]), Number(p[1])] as GeometryPoint,
    );
    upsertRoiMeta(uuid, {
      title: d.title,
      points,
      volumetric: d.volumetric,
      height: d.height,
      buffer_size: d.buffer_size,
      range_max: d.range_max,
      sectors: d.sectors,
    });
  }
  for (const id of Array.from(rois.keys())) {
    if (!keep.has(id)) {
      rois.delete(id);
    }
  }
  flushGeometryToHidden();
  notify();
}

export function ingestStringifyTrips(
  drafts: Array<{
    uuid?: string;
    title?: string;
    points?: number[][];
  }>,
): void {
  const keep = new Set<string>();
  for (const d of drafts) {
    const uuid = String(d.uuid || "").trim();
    if (!uuid) {
      continue;
    }
    keep.add(uuid);
    const points = (d.points || []).map(
      (p) => [Number(p[0]), Number(p[1])] as GeometryPoint,
    );
    upsertTripMeta(uuid, { title: d.title, points });
  }
  for (const id of Array.from(trips.keys())) {
    if (!keep.has(id)) {
      trips.delete(id);
    }
  }
  flushGeometryToHidden();
  notify();
}

export function flushGeometryToHidden(): void {
  const roiPayload = getRoiList().map((r) => ({
    title: r.title,
    uuid: r.uuid,
    points: r.points,
    volumetric: r.volumetric,
    height: r.height,
    buffer_size: r.buffer_size,
    range_max: r.range_max,
    sectors: r.sectors,
  }));
  const tripPayload = getTripwireList().map((t) => ({
    title: t.title,
    uuid: t.uuid,
    points: t.points,
  }));
  writeInput("id_rois", JSON.stringify(roiPayload));
  writeInput("tripwires", JSON.stringify(tripPayload));
}

export function resetGeometryModel(): void {
  rois = new Map();
  trips = new Map();
  notify();
}
