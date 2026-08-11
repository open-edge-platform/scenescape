// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";
import { metersToPixels, pixelsToMeters } from "../scene/map/coords";
import "./SensorAreaMap.css";

export type SensorAreaMode = "scene" | "circle" | "poly";

type Props = {
  mapUrl: string;
  scale: number;
  area: SensorAreaMode;
  centerX: number;
  centerY: number;
  radius: number;
  points: [number, number][];
  onCenterChange: (x: number, y: number) => void;
  onRadiusChange: (r: number) => void;
  onPointsChange: (pts: [number, number][]) => void;
};

type MapSize = { width: number; height: number };

function svgLocalPoint(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
): [number, number] | null {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) {
    return null;
  }
  const loc = pt.matrixTransform(ctm.inverse());
  return [loc.x, loc.y];
}

/**
 * Click-to-place circle center / polygon vertices on the scene map.
 * Matches the legacy singletonCal map interaction without Snap.
 */
export function SensorAreaMap({
  mapUrl,
  scale,
  area,
  centerX,
  centerY,
  radius,
  points,
  onCenterChange,
  onRadiusChange,
  onPointsChange,
}: Props) {
  const [size, setSize] = useState<MapSize | null>(null);
  const [draft, setDraft] = useState<[number, number][]>([]);

  useEffect(() => {
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (
        !cancelled &&
        img.naturalWidth > 0 &&
        img.naturalHeight > 0
      ) {
        setSize({ width: img.naturalWidth, height: img.naturalHeight });
      }
    };
    img.src = mapUrl;
    return () => {
      cancelled = true;
    };
  }, [mapUrl]);

  useEffect(() => {
    setDraft([]);
  }, [area]);

  const sceneYMax = size?.height || 1;
  const safeScale = scale > 0 ? scale : 100;

  const centerPx = useMemo(
    () => metersToPixels(centerX, centerY, safeScale, sceneYMax),
    [centerX, centerY, safeScale, sceneYMax],
  );
  const radiusPx = Math.max(4, radius * safeScale);
  const committedPx = useMemo(
    () => points.map((p) => metersToPixels(p[0], p[1], safeScale, sceneYMax)),
    [points, safeScale, sceneYMax],
  );
  const draftPx = useMemo(
    () => draft.map((p) => metersToPixels(p[0], p[1], safeScale, sceneYMax)),
    [draft, safeScale, sceneYMax],
  );

  const toMeters = (x: number, y: number): [number, number] =>
    pixelsToMeters(x, y, safeScale, sceneYMax);

  const onSvgClick = (ev: React.MouseEvent<SVGSVGElement>) => {
    if (area === "scene") {
      return;
    }
    const loc = svgLocalPoint(ev.currentTarget, ev.clientX, ev.clientY);
    if (!loc) {
      return;
    }
    const meters = toMeters(loc[0], loc[1]);
    if (area === "circle") {
      onCenterChange(meters[0], meters[1]);
      return;
    }
    if (!draft.length && points.length >= 3) {
      return;
    }
    if (draft.length >= 3) {
      const first = draftPx[0];
      if (first && Math.hypot(loc[0] - first[0], loc[1] - first[1]) < 12) {
        onPointsChange(draft);
        setDraft([]);
        return;
      }
    }
    setDraft((prev) => [...prev, meters]);
  };

  const dragCenter = (ev: React.MouseEvent) => {
    ev.stopPropagation();
    ev.preventDefault();
    const svg = (ev.target as SVGElement).ownerSVGElement;
    if (!svg) {
      return;
    }
    const move = (e: MouseEvent) => {
      const loc = svgLocalPoint(svg, e.clientX, e.clientY);
      if (!loc) {
        return;
      }
      const meters = toMeters(loc[0], loc[1]);
      onCenterChange(meters[0], meters[1]);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const dragRadius = (ev: React.MouseEvent) => {
    ev.stopPropagation();
    ev.preventDefault();
    const svg = (ev.target as SVGElement).ownerSVGElement;
    if (!svg) {
      return;
    }
    const move = (e: MouseEvent) => {
      const loc = svgLocalPoint(svg, e.clientX, e.clientY);
      if (!loc) {
        return;
      }
      const distPx = Math.hypot(loc[0] - centerPx[0], loc[1] - centerPx[1]);
      onRadiusChange(Math.max(0.1, distPx / safeScale));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const dragVertex = (index: number, ev: React.MouseEvent) => {
    ev.stopPropagation();
    ev.preventDefault();
    const svg = (ev.target as SVGElement).ownerSVGElement;
    if (!svg) {
      return;
    }
    const source = draft.length ? draft : points;
    const move = (e: MouseEvent) => {
      const loc = svgLocalPoint(svg, e.clientX, e.clientY);
      if (!loc) {
        return;
      }
      const next = source.map((p, i) =>
        i === index ? toMeters(loc[0], loc[1]) : p,
      ) as [number, number][];
      if (draft.length) {
        setDraft(next);
      } else {
        onPointsChange(next);
      }
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  if (!size) {
    return (
      <p className="ss-workspace-panel-hint">Loading scene map…</p>
    );
  }

  const drawing = area === "circle" || area === "poly";
  const livePoly = draftPx.length ? draftPx : committedPx;

  return (
    <svg
      className={`ss-sensor-area-map${drawing ? " is-drawing" : ""}`}
      viewBox={`0 0 ${size.width} ${size.height}`}
      preserveAspectRatio="xMidYMid meet"
      width="100%"
      height="100%"
      onClick={onSvgClick}
      role="img"
      aria-label="Sensor coverage map"
    >
      <image
        href={mapUrl}
        x={0}
        y={0}
        width={size.width}
        height={size.height}
        preserveAspectRatio="none"
      />
      {area === "circle" ? (
        <g className="ss-sensor-area-circle">
          <circle
            className="ss-sensor-area-coverage"
            cx={centerPx[0]}
            cy={centerPx[1]}
            r={radiusPx}
            onMouseDown={dragRadius}
            onClick={(ev) => ev.stopPropagation()}
          />
          <circle
            className="ss-sensor-area-handle"
            cx={centerPx[0]}
            cy={centerPx[1]}
            r={7}
            onMouseDown={dragCenter}
            onClick={(ev) => ev.stopPropagation()}
          />
        </g>
      ) : null}
      {area === "poly" && livePoly.length > 0 ? (
        <g className="ss-sensor-area-poly">
          {livePoly.length >= 2 ? (
            draft.length ? (
              <polyline
                className="ss-sensor-area-draft"
                points={livePoly.map((p) => p.join(",")).join(" ")}
              />
            ) : (
              <polygon
                className="ss-sensor-area-coverage"
                points={livePoly.map((p) => p.join(",")).join(" ")}
              />
            )
          ) : null}
          {livePoly.map((p, i) => (
            <circle
              key={i}
              className={
                i === 0 && draft.length >= 3
                  ? "ss-sensor-area-handle is-close"
                  : "ss-sensor-area-handle"
              }
              cx={p[0]}
              cy={p[1]}
              r={6}
              onMouseDown={(ev) => {
                if (i === 0 && draft.length >= 3) {
                  return;
                }
                dragVertex(i, ev);
              }}
              onClick={(ev) => {
                ev.stopPropagation();
                if (i === 0 && draft.length >= 3) {
                  onPointsChange(draft);
                  setDraft([]);
                }
              }}
            />
          ))}
        </g>
      ) : null}
    </svg>
  );
}
