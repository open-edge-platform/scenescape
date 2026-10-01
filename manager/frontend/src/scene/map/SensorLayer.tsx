// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { memo, useEffect, useMemo, useState } from "react";
import { metersToPixels } from "./coords";
import type { SceneSensorBootstrap } from "../types";

type AreaPayload = {
  area?: string;
  x?: number;
  y?: number;
  radius?: number;
  points?: number[][];
  title?: string;
};

type LiveValue = { value: string; status: string };

type Props = {
  sensors: SceneSensorBootstrap[];
  scale: number;
  sceneYMax: number;
};

function parseArea(raw: string): AreaPayload | null {
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as AreaPayload;
  } catch {
    return null;
  }
}

function hasMapGeometry(sensor: AreaPayload | null): boolean {
  if (!sensor || !sensor.area || sensor.area === "scene") {
    return false;
  }
  if (sensor.area === "circle") {
    return (
      Number.isFinite(Number(sensor.x)) &&
      Number.isFinite(Number(sensor.y)) &&
      Number.isFinite(Number(sensor.radius))
    );
  }
  if (sensor.area === "poly") {
    return Array.isArray(sensor.points) && sensor.points.length >= 3;
  }
  return false;
}

function polyCenter(flat: number[]): [number, number] {
  let sx = 0;
  let sy = 0;
  const n = flat.length / 2;
  for (let i = 0; i < flat.length; i += 2) {
    sx += flat[i];
    sy += flat[i + 1];
  }
  return [sx / n, sy / n];
}

/**
 * Draw singleton sensors on the React map (replaces Snap ssDrawSingletonSensors).
 */
export const SensorLayer = memo(function SensorLayer({
  sensors,
  scale,
  sceneYMax,
}: Props) {
  const [live, setLive] = useState<Record<string, LiveValue>>({});

  useEffect(() => {
    const onSingleton = (ev: Event) => {
      const detail = (
        ev as CustomEvent<{ id?: string; value?: unknown; status?: string }>
      ).detail;
      if (!detail?.id) {
        return;
      }
      setLive((prev) => ({
        ...prev,
        [detail.id!]: {
          value: detail.value != null ? String(detail.value) : "",
          status: detail.status || "",
        },
      }));
    };
    window.addEventListener("ss-singleton", onSingleton);
    return () => window.removeEventListener("ss-singleton", onSingleton);
  }, []);

  const drawn = useMemo(() => {
    return sensors
      .map((row) => {
        const area = parseArea(row.areaJson);
        if (!hasMapGeometry(area) || !area) {
          return null;
        }
        return { row, area };
      })
      .filter(Boolean) as { row: SceneSensorBootstrap; area: AreaPayload }[];
  }, [sensors]);

  return (
    <g className="ss-react-sensor-layer" pointerEvents="none">
      {drawn.map(({ row, area }) => {
        const liveVal = live[row.sensorId];
        const fill = liveVal?.status || undefined;
        const title = (area.title || row.name || "").trim();
        if (area.area === "circle") {
          const [cx, cy] = metersToPixels(
            Number(area.x),
            Number(area.y),
            scale,
            sceneYMax,
          );
          const r = Number(area.radius) * scale;
          return (
            <g
              key={row.sensorId}
              id={`sensor_${row.sensorId}`}
              className="area-group ss-react-sensor"
            >
              <circle
                className="area"
                cx={cx}
                cy={cy}
                r={r}
                style={fill ? { fill } : undefined}
              />
              <circle className="sensor" cx={cx} cy={cy} r={7} />
              <text className="value" x={cx} y={cy} textAnchor="middle">
                {liveVal?.value || ""}
              </text>
              <text
                id="name"
                x={cx + 10}
                y={cy - 10}
                textAnchor="start"
                className="ss-react-sensor-name"
              >
                {title}
              </text>
            </g>
          );
        }
        const flat: number[] = [];
        (area.points || []).forEach((m) => {
          const [px, py] = metersToPixels(
            Number(m[0]),
            Number(m[1]),
            scale,
            sceneYMax,
          );
          flat.push(px, py);
        });
        if (flat.length < 6) {
          return null;
        }
        const [mx, my] = polyCenter(flat);
        const points = flat.reduce<string[]>((acc, v, i) => {
          if (i % 2 === 0) {
            acc.push(`${v},${flat[i + 1]}`);
          }
          return acc;
        }, []);
        return (
          <g
            key={row.sensorId}
            id={`sensor_${row.sensorId}`}
            className="area-group ss-react-sensor"
          >
            <polygon
              className="area"
              points={points.join(" ")}
              style={fill ? { fill } : undefined}
            />
            <circle className="sensor" cx={mx} cy={my} r={7} />
            <text className="value" x={mx} y={my} textAnchor="middle">
              {liveVal?.value || ""}
            </text>
            <text
              id="name"
              x={mx + 10}
              y={my - 10}
              textAnchor="start"
              className="ss-react-sensor-name"
            >
              {title}
            </text>
          </g>
        );
      })}
    </g>
  );
});
