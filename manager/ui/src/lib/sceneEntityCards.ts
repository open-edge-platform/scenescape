// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type {
  SceneCameraBootstrap,
  SceneChildBootstrap,
  SceneSensorBootstrap,
} from "../scene/types";

function asStr(v: unknown, fallback = ""): string {
  if (v == null || v === "") {
    return fallback;
  }
  return String(v);
}

function numericPk(v: unknown): string | null {
  if (v == null || v === "") {
    return null;
  }
  const s = String(v);
  return /^\d+$/.test(s) ? s : null;
}

function areaJsonFromRest(data: Record<string, unknown>): string | null {
  if (
    data.area == null &&
    data.center == null &&
    data.points == null &&
    data.radius == null
  ) {
    return null;
  }
  const center = Array.isArray(data.center) ? data.center : null;
  const colorRanges = data.color_ranges as
    | { sectors?: unknown; range_max?: unknown }
    | undefined;
  return JSON.stringify({
    area: data.area ?? "scene",
    radius: data.radius ?? null,
    x: center ? center[0] : null,
    y: center ? center[1] : null,
    points: Array.isArray(data.points) ? data.points : [],
    sectors: {
      thresholds: colorRanges?.sectors ?? [],
      range_max: colorRanges?.range_max ?? null,
    },
  });
}

export function restDestId(
  data: Record<string, unknown>,
  key: "scene" | "parent",
): string {
  return asStr(data[key]);
}

export function cameraCardFromRest(
  data: Record<string, unknown>,
): SceneCameraBootstrap | null {
  const pk = numericPk(data.id);
  const sensorId = asStr(data.sensor_id || data.uid);
  const name = asStr(data.name, sensorId);
  if (!pk && !sensorId) {
    return null;
  }
  const id = pk || sensorId;
  return {
    id,
    sensorId: sensorId || id,
    name: name || sensorId || id,
    calibrateHref: `?ss=calibrate-cam&id=${id}`,
    cmdTopic: `scenescape/cmd/camera/${sensorId || id}`,
    deleteUrl: pk ? `/cam/delete/${pk}/` : null,
  };
}

export function sensorCardFromRest(
  data: Record<string, unknown>,
  existing?: SceneSensorBootstrap,
): SceneSensorBootstrap | null {
  const pk = numericPk(data.id);
  const sensorId = asStr(data.sensor_id || data.uid);
  const name = asStr(data.name, sensorId);
  if (!pk && !sensorId) {
    return null;
  }
  const id = pk || sensorId;
  return {
    id,
    sensorId: sensorId || id,
    name: name || sensorId || id,
    iconUrl: existing?.iconUrl ?? null,
    areaJson: areaJsonFromRest(data) || existing?.areaJson || "{}",
    calibrateHref: `?ss=calibrate-sensor&id=${id}`,
    editHref: `?ss=sensor-edit&id=${sensorId || id}`,
    deleteUrl: pk
      ? `/singleton_sensor/delete/${pk}/`
      : (existing?.deleteUrl ?? null),
  };
}

export function childCardFromRest(
  data: Record<string, unknown>,
  scenes: { id: string; name: string }[],
  existing?: SceneChildBootstrap,
): SceneChildBootstrap | null {
  const pk = asStr(data.uid || data.id);
  if (!pk) {
    return null;
  }
  const childType = asStr(data.child_type || existing?.childType, "local");
  const childSceneId = data.child != null ? asStr(data.child) : null;
  const remoteChildId =
    data.remote_child_id != null
      ? asStr(data.remote_child_id)
      : (existing?.remoteChildId ?? null);
  const sceneName = childSceneId
    ? scenes.find((s) => s.id === childSceneId)?.name
    : undefined;
  const name = asStr(
    data.name || data.child_name || sceneName || existing?.name,
    "Child",
  );
  const restUid =
    childType === "local" && childSceneId
      ? childSceneId
      : remoteChildId || pk;
  return {
    id: pk,
    name,
    childType,
    remoteChildId,
    detailUrl: childSceneId
      ? `/${childSceneId}/`
      : (existing?.detailUrl ?? null),
    thumbnailUrl: existing?.thumbnailUrl ?? null,
    mapUrl: existing?.mapUrl ?? null,
    restUid,
    editHref: `?ss=child-edit&id=${restUid}`,
    deleteUrl: /^\d+$/.test(pk)
      ? `/child/delete/${pk}/`
      : (existing?.deleteUrl ?? null),
  };
}

export function upsertCameraCard(
  list: SceneCameraBootstrap[],
  card: SceneCameraBootstrap,
  prevSensorId?: string | null,
): SceneCameraBootstrap[] {
  const idx = list.findIndex(
    (item) =>
      item.id === card.id ||
      item.sensorId === card.sensorId ||
      Boolean(prevSensorId && item.sensorId === prevSensorId),
  );
  if (idx < 0) {
    return [...list, card];
  }
  const next = list.slice();
  next[idx] = {
    ...list[idx],
    ...card,
    deleteUrl: card.deleteUrl || list[idx].deleteUrl,
  };
  return next;
}

export function upsertSensorCard(
  list: SceneSensorBootstrap[],
  card: SceneSensorBootstrap,
  prevSensorId?: string | null,
): SceneSensorBootstrap[] {
  const idx = list.findIndex(
    (item) =>
      item.id === card.id ||
      item.sensorId === card.sensorId ||
      Boolean(prevSensorId && item.sensorId === prevSensorId),
  );
  if (idx < 0) {
    return [...list, card];
  }
  const next = list.slice();
  next[idx] = {
    ...list[idx],
    ...card,
    iconUrl: card.iconUrl ?? list[idx].iconUrl,
    areaJson: card.areaJson || list[idx].areaJson,
    deleteUrl: card.deleteUrl || list[idx].deleteUrl,
  };
  return next;
}

export function upsertChildCard(
  list: SceneChildBootstrap[],
  card: SceneChildBootstrap,
  prevRestUid?: string | null,
): SceneChildBootstrap[] {
  const idx = list.findIndex(
    (item) =>
      item.id === card.id ||
      item.restUid === card.restUid ||
      Boolean(prevRestUid && item.restUid === prevRestUid),
  );
  if (idx < 0) {
    return [...list, card];
  }
  const next = list.slice();
  next[idx] = {
    ...list[idx],
    ...card,
    thumbnailUrl: card.thumbnailUrl ?? list[idx].thumbnailUrl,
    mapUrl: card.mapUrl ?? list[idx].mapUrl,
    detailUrl: card.detailUrl ?? list[idx].detailUrl,
    deleteUrl: card.deleteUrl || list[idx].deleteUrl,
  };
  return next;
}
