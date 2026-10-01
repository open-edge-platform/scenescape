// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * Imperative live marks / trails on React `#svgout` (ports marks.js plot).
 * Uses DOM mutation + rAF-friendly calls — not React state per MQTT frame.
 * BAT expects class `mark` and a changing `transform` attribute.
 */

const SVG_NS = "http://www.w3.org/2000/svg";
const MAX_TRAIL_SEGMENTS = 300;

export type SceneObjectMark = {
  id: string | number;
  type?: string;
  translation?: number[] | { x?: number; y?: number };
  tag_id?: string | number;
  persistent_data?: Record<string, unknown>;
};

type MarkEntry = {
  el: SVGGElement;
  x: number;
  y: number;
};

const marks = new Map<string, MarkEntry>();
const trails = new Map<string, SVGGElement>();

let layerHost: SVGGElement | null = null;
let showTrails = false;
let assetColors: Record<string, string> = {};
let mapScale = 100;
let sceneYMax = 1000;

function metersToPixelsRounded(
  mx: number,
  my: number,
  scale: number,
  yMax: number,
): [number, number] {
  return [Math.round(mx * scale), Math.round(yMax - my * scale)];
}

function translationToMeters(t: SceneObjectMark["translation"]): [number, number] | null {
  if (!t) {
    return null;
  }
  if (Array.isArray(t) && t.length >= 2) {
    return [Number(t[0]), Number(t[1])];
  }
  if (typeof t === "object") {
    const x = Number((t as { x?: number }).x);
    const y = Number((t as { y?: number }).y);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      return [x, y];
    }
  }
  return null;
}

function quadrantPath(r: number, startDeg: number, endDeg: number): string {
  const start = (startDeg * Math.PI) / 180;
  const end = (endDeg * Math.PI) / 180;
  const x1 = r * Math.cos(start);
  const y1 = r * Math.sin(start);
  const x2 = r * Math.cos(end);
  const y2 = r * Math.sin(end);
  return `M0,0 L${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2} Z`;
}

function ensureLayer(): SVGGElement | null {
  if (layerHost && layerHost.isConnected) {
    return layerHost;
  }
  const svg = document.getElementById("svgout");
  if (!svg) {
    return null;
  }
  let g = svg.querySelector("g.ss-react-marks-layer") as SVGGElement | null;
  if (!g) {
    g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "ss-react-marks-layer");
    g.setAttribute("pointer-events", "none");
    svg.appendChild(g);
  }
  layerHost = g;
  return g;
}

function radiusForType(type: string | undefined, scale: number): number {
  if (type === "person") {
    return Math.max(1, Math.round(scale * 0.3));
  }
  if (type === "vehicle") {
    return Math.max(1, Math.round(scale * 1.5));
  }
  if (type === "apriltag") {
    return Math.max(1, Math.round(scale * 0.15));
  }
  return Math.max(1, Math.round(scale * 0.5));
}

function ensureTrail(id: string, type: string): SVGGElement | null {
  const host = ensureLayer();
  if (!host) {
    return null;
  }
  let trail = trails.get(id);
  if (trail && trail.isConnected) {
    return trail;
  }
  trail = document.createElementNS(SVG_NS, "g");
  trail.setAttribute("id", `trail_${id}`);
  trail.setAttribute("class", `trail ${type}`);
  host.insertBefore(trail, host.firstChild);
  trails.set(id, trail);
  return trail;
}

function appendTrailSegment(
  trail: SVGGElement,
  prevX: number,
  prevY: number,
  x: number,
  y: number,
  color: string,
): void {
  if (prevX === x && prevY === y) {
    return;
  }
  const line = document.createElementNS(SVG_NS, "line");
  line.setAttribute("x1", String(prevX));
  line.setAttribute("y1", String(prevY));
  line.setAttribute("x2", String(x));
  line.setAttribute("y2", String(y));
  line.setAttribute("stroke", color);
  trail.appendChild(line);
  while (trail.childNodes.length > MAX_TRAIL_SEGMENTS) {
    trail.removeChild(trail.childNodes[0]);
  }
}

function removeExpired(ids: Set<string>): void {
  ids.forEach((id) => {
    const mark = marks.get(id);
    if (mark) {
      mark.el.remove();
      marks.delete(id);
    }
    const trail = trails.get(id);
    if (trail) {
      trail.remove();
      trails.delete(id);
    }
  });
}

function addNewMark(
  o: SceneObjectMark,
  x: number,
  y: number,
): MarkEntry | null {
  const host = ensureLayer();
  if (!host) {
    return null;
  }
  const id = String(o.id);
  const type = o.type || "unknown";
  const g = document.createElementNS(SVG_NS, "g");
  g.setAttribute("id", `mark_${id}`);
  g.setAttribute("class", `mark ${type}`);
  // Snap used "T x,y"; BAT compares transform changing over time.
  g.setAttribute("transform", `translate(${x},${y})`);

  const trackColor = `#${id.substring(0, 6)}`;
  g.setAttribute("data-color", trackColor);

  const r = radiusForType(type, mapScale);
  if (type === "apriltag") {
    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("cx", "0");
    circle.setAttribute("cy", "0");
    circle.setAttribute("r", String(r));
    circle.setAttribute("class", "mark-core");
    circle.setAttribute("stroke", trackColor);
    circle.setAttribute("fill", "none");
    g.appendChild(circle);
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", "0");
    text.setAttribute("y", "0");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dominant-baseline", "central");
    text.textContent = String(o.tag_id ?? "");
    g.appendChild(text);
  } else {
    const coreRadius = Math.max(7, Math.round(r * 0.4));
    const baseColor = assetColors[type] || "black";
    const colors = [baseColor, trackColor, baseColor, trackColor];
    for (let i = 0; i < 4; i += 1) {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", quadrantPath(coreRadius, i * 90, (i + 1) * 90));
      path.setAttribute("class", "mark-core");
      path.setAttribute("fill", colors[i]);
      g.appendChild(path);
    }
  }

  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = id;
  g.appendChild(title);

  host.appendChild(g);
  const entry = { el: g, x, y };
  marks.set(id, entry);
  return entry;
}

export function configureLiveMarks(options: {
  scale: number;
  sceneYMax: number;
  assetMarkColors?: Record<string, string>;
}): void {
  mapScale = options.scale > 0 ? options.scale : 100;
  sceneYMax = options.sceneYMax > 0 ? options.sceneYMax : 1000;
  if (options.assetMarkColors) {
    assetColors = { ...options.assetMarkColors };
  }
  ensureLayer();
}

export function setLiveMarksShowTrails(on: boolean): void {
  showTrails = on;
  if (!on) {
    clearLiveTrails();
  }
}

export function clearLiveTrails(): void {
  trails.forEach((el) => el.remove());
  trails.clear();
}

export function clearLiveMarks(): void {
  marks.forEach((m) => m.el.remove());
  marks.clear();
  clearLiveTrails();
  layerHost = null;
}

/** Plot one regulated-scene frame of objects onto the React marks layer. */
export function plotLiveMarks(objects: SceneObjectMark[] | null | undefined): void {
  if (!ensureLayer()) {
    return;
  }
  const list = Array.isArray(objects) ? objects : [];
  if (!list.length) {
    if (marks.size) {
      removeExpired(new Set(marks.keys()));
    }
    return;
  }

  const oldIds = new Set(marks.keys());
  const newIds = new Set<string>();
  list.forEach((o) => newIds.add(String(o.id)));
  newIds.forEach((id) => oldIds.delete(id));
  removeExpired(oldIds);

  list.forEach((o) => {
    const meters = translationToMeters(o.translation);
    if (!meters) {
      return;
    }
    const [x, y] = metersToPixelsRounded(
      meters[0],
      meters[1],
      mapScale,
      sceneYMax,
    );
    const id = String(o.id);
    let entry = marks.get(id);
    if (entry) {
      const prevX = entry.x;
      const prevY = entry.y;
      if (prevX !== x || prevY !== y) {
        entry.el.setAttribute("transform", `translate(${x},${y})`);
        entry.x = x;
        entry.y = y;
      }
      if (showTrails) {
        const trail = ensureTrail(id, o.type || "unknown");
        if (trail) {
          appendTrailSegment(
            trail,
            prevX,
            prevY,
            x,
            y,
            entry.el.getAttribute("data-color") || "#888",
          );
        }
      }
    } else {
      const created = addNewMark(o, x, y);
      if (created && showTrails) {
        ensureTrail(id, o.type || "unknown");
      }
    }
  });
}
