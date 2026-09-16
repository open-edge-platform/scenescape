// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/** Live occupancy / track marks on the React map (Phase 4b start). */

const marks = new Map<string, SVGCircleElement>();

function findMapSvg(): Element | null {
  return document.getElementById("svgout");
}

export function plotLiveMark(
  id: string,
  xPx: number,
  yPx: number,
  color = "#0054ae",
): void {
  const svg = findMapSvg();
  if (!svg) {
    return;
  }
  let circle = marks.get(id);
  if (!circle) {
    circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("class", "ss-live-mark");
    circle.setAttribute("r", "6");
    circle.setAttribute("data-mark-id", id);
    svg.appendChild(circle);
    marks.set(id, circle);
  }
  circle.setAttribute("cx", String(xPx));
  circle.setAttribute("cy", String(yPx));
  circle.setAttribute("fill", color);
}

export function clearLiveMarks(): void {
  marks.forEach((el) => el.remove());
  marks.clear();
}
