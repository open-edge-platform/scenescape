// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type RoiSector = {
  color: string;
  color_min: number | string;
};

export type RoiEntity = {
  svgId: string;
  uuid: string;
  title: string;
  volumetric: boolean;
  height: number;
  buffer_size: number;
  greenMin: number;
  yellowMin: number;
  redMin: number;
  rangeMax: number;
  topic: string;
  readOnly?: boolean;
};

export type TripwireEntity = {
  svgId: string;
  uuid: string;
  title: string;
  topic: string;
  readOnly?: boolean;
};

export type RoiLoadJson = {
  title?: string;
  uuid?: string;
  volumetric?: boolean;
  height?: number;
  buffer_size?: number;
  sectors?: {
    thresholds?: RoiSector[];
    range_max?: number;
  };
  points?: number[][];
};

export type TripwireLoadJson = {
  title?: string;
  uuid?: string;
  points?: number[][];
};

export function sectorMin(
  thresholds: RoiSector[] | undefined,
  color: string,
  fallback: number,
): number {
  const hit = thresholds?.find((t) => t.color === color);
  if (!hit) {
    return fallback;
  }
  const n = Number(hit.color_min);
  return Number.isFinite(n) ? n : fallback;
}

export function roiFromLoad(
  raw: RoiLoadJson,
  sceneId: string,
): RoiEntity | null {
  const uuid = String(raw.uuid || "").trim();
  if (!uuid) {
    return null;
  }
  const thresholds = raw.sectors?.thresholds || [];
  return {
    svgId: `roi_${uuid}`,
    uuid,
    title: (raw.title || "").trim(),
    volumetric: Boolean(raw.volumetric),
    height: Number(raw.height ?? 1.0),
    buffer_size: Number(raw.buffer_size ?? 0.0),
    greenMin: sectorMin(thresholds, "green", 0),
    yellowMin: sectorMin(thresholds, "yellow", 2),
    redMin: sectorMin(thresholds, "red", 5),
    rangeMax: Number(raw.sectors?.range_max ?? 10),
    topic: `scenescape/event/region/${sceneId}/${uuid}/count`,
  };
}

export function tripwireFromLoad(
  raw: TripwireLoadJson,
  sceneId: string,
): TripwireEntity | null {
  const uuid = String(raw.uuid || "").trim();
  if (!uuid) {
    return null;
  }
  return {
    svgId: `tripwire_${uuid}`,
    uuid,
    title: (raw.title || "").trim(),
    topic: `scenescape/event/tripwire/${sceneId}/${uuid}/objects`,
  };
}
