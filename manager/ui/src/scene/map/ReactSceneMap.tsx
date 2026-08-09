// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getRoiList,
  getTripwireList,
  replaceRoiPoints,
  replaceTripPoints,
  subscribeGeometry,
  upsertRoiMeta,
  upsertTripMeta,
  type GeometryPoint,
  type RoiGeometry,
  type TripwireGeometry,
} from "./geometryModel";
import {
  metersToPixels,
  pixelsToMeters,
  readMapScale,
  readSceneYMax,
} from "./coords";
import "./reactSceneMap.css";

type Mode = "idle" | "add-roi" | "add-trip";

type Props = {
  mapHref: string;
  mapWidth: number;
  mapHeight: number;
};

function newTempId(): string {
  return `tmp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * React SVG scene map — draw/edit ROI polygons and tripwires.
 * Enabled when window.ssUseReactMap is true (set from SceneDetailPage).
 */
export function ReactSceneMap({ mapHref, mapWidth, mapHeight }: Props) {
  const [rois, setRois] = useState<RoiGeometry[]>(() => getRoiList());
  const [trips, setTrips] = useState<TripwireGeometry[]>(() =>
    getTripwireList(),
  );
  const [mode, setMode] = useState<Mode>("idle");
  const [draft, setDraft] = useState<GeometryPoint[]>([]);
  const scale = readMapScale();
  const sceneYMax = mapHeight || readSceneYMax(mapHeight);

  useEffect(
    () =>
      subscribeGeometry(() => {
        setRois(getRoiList());
        setTrips(getTripwireList());
      }),
    [],
  );

  useEffect(() => {
    const startRoi = () => {
      setMode("add-roi");
      setDraft([]);
    };
    const startTrip = () => {
      setMode("add-trip");
      setDraft([]);
    };
    window.ssMapReact = { startAddRoi: startRoi, startAddTripwire: startTrip };
    const onClick = (ev: Event) => {
      const t = ev.target as HTMLElement | null;
      if (!t) {
        return;
      }
      const btn = t.closest(
        "#new-roi, #empty-new-roi, #new-tripwire, #empty-new-tripwire",
      ) as HTMLElement | null;
      if (!btn) {
        return;
      }
      ev.preventDefault();
      if (btn.id.includes("trip")) {
        startTrip();
      } else {
        startRoi();
      }
    };
    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      delete window.ssMapReact;
    };
  }, []);

  const toPx = useCallback(
    (p: GeometryPoint): [number, number] =>
      metersToPixels(p[0], p[1], scale, sceneYMax),
    [scale, sceneYMax],
  );

  const onSvgClick = (ev: React.MouseEvent<SVGSVGElement>) => {
    if (mode === "idle") {
      return;
    }
    const svg = ev.currentTarget;
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) {
      return;
    }
    const loc = pt.matrixTransform(ctm.inverse());
    const meters = pixelsToMeters(loc.x, loc.y, scale, sceneYMax);

    if (mode === "add-roi") {
      if (draft.length >= 3) {
        const first = toPx(draft[0]);
        const dx = loc.x - first[0];
        const dy = loc.y - first[1];
        if (Math.hypot(dx, dy) < 12) {
          const uuid = newTempId();
          upsertRoiMeta(uuid, {
            title: "",
            points: draft,
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
          window.dispatchEvent(
            new CustomEvent("ss-roi-form-add", {
              detail: {
                svgId: `roi_${uuid}`,
                uuid,
                title: "",
              },
            }),
          );
          setDraft([]);
          setMode("idle");
          return;
        }
      }
      setDraft((d) => [...d, meters]);
      return;
    }

    if (mode === "add-trip") {
      const next = [...draft, meters];
      if (next.length >= 2) {
        const uuid = newTempId();
        upsertTripMeta(uuid, { title: "", points: next.slice(0, 2) });
        window.dispatchEvent(
          new CustomEvent("ss-tripwire-form-add", {
            detail: { svgId: `tripwire_${uuid}`, uuid, title: "" },
          }),
        );
        setDraft([]);
        setMode("idle");
      } else {
        setDraft(next);
      }
    }
  };

  const dragVertex = (
    kind: "roi" | "trip",
    uuid: string,
    index: number,
    ev: React.MouseEvent,
  ) => {
    ev.stopPropagation();
    ev.preventDefault();
    const svg = (ev.target as SVGElement).ownerSVGElement;
    if (!svg) {
      return;
    }
    const move = (e: MouseEvent) => {
      const pt = svg.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const ctm = svg.getScreenCTM();
      if (!ctm) {
        return;
      }
      const loc = pt.matrixTransform(ctm.inverse());
      const meters = pixelsToMeters(loc.x, loc.y, scale, sceneYMax);
      if (kind === "roi") {
        const roi = getRoiList().find((r) => r.uuid === uuid);
        if (!roi) {
          return;
        }
        const points = roi.points.map((p, i) =>
          i === index ? meters : p,
        ) as GeometryPoint[];
        replaceRoiPoints(uuid, points);
      } else {
        const trip = getTripwireList().find((t) => t.uuid === uuid);
        if (!trip) {
          return;
        }
        const points = trip.points.map((p, i) =>
          i === index ? meters : p,
        ) as GeometryPoint[];
        replaceTripPoints(uuid, points);
      }
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const draftPx = useMemo(() => draft.map(toPx), [draft, toPx]);

  return (
    // Own hard-contract `#svgout` while active; Snap canvas is renamed to
    // `#svgout-snap` by SceneMapPane so lookups hit this visible map.
    <svg
      id="svgout"
      className={`ss-react-scene-map${mode !== "idle" ? ` is-${mode}` : ""}`}
      viewBox={`0 0 ${mapWidth} ${mapHeight}`}
      width="100%"
      height="100%"
      onClick={onSvgClick}
    >
      <image
        href={mapHref}
        x={0}
        y={0}
        width={mapWidth}
        height={mapHeight}
        preserveAspectRatio="none"
      />
      {rois.map((roi) => {
        const pts = roi.points.map(toPx);
        const pointsAttr = pts.map((p) => p.join(",")).join(" ");
        return (
          <g key={roi.uuid} id={`roi_${roi.uuid}`} className="roi">
            <polygon points={pointsAttr} className="ss-react-roi-poly" />
            {pts.map((p, i) => (
              <circle
                key={i}
                className="ss-react-vertex"
                cx={p[0]}
                cy={p[1]}
                r={6}
                onMouseDown={(ev) => dragVertex("roi", roi.uuid, i, ev)}
              />
            ))}
          </g>
        );
      })}
      {trips.map((trip) => {
        const pts = trip.points.map(toPx);
        if (pts.length < 2) {
          return null;
        }
        return (
          <g key={trip.uuid} id={`tripwire_${trip.uuid}`} className="tripwire">
            <line
              className="tripline ss-react-trip-line"
              x1={pts[0][0]}
              y1={pts[0][1]}
              x2={pts[1][0]}
              y2={pts[1][1]}
            />
            {pts.map((p, i) => (
              <circle
                key={i}
                className="ss-react-vertex"
                cx={p[0]}
                cy={p[1]}
                r={6}
                onMouseDown={(ev) => dragVertex("trip", trip.uuid, i, ev)}
              />
            ))}
          </g>
        );
      })}
      {draftPx.length > 0 ? (
        <g className="ss-react-draft">
          {mode === "add-roi" && draftPx.length >= 2 ? (
            <polyline
              points={draftPx.map((p) => p.join(",")).join(" ")}
              className="ss-react-draft-line"
            />
          ) : null}
          {draftPx.map((p, i) => (
            <circle
              key={i}
              cx={p[0]}
              cy={p[1]}
              r={5}
              className="ss-react-draft-pt"
            />
          ))}
        </g>
      ) : null}
    </svg>
  );
}

declare global {
  interface Window {
    ssUseReactMap?: boolean;
    ssMapReact?: {
      startAddRoi: () => void;
      startAddTripwire: () => void;
    };
  }
}
