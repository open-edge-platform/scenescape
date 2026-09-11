// SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import { metersToPixels } from "/static/js/utils.js";

var mark_radius = 9;
var marks = {}; // Global object to store marks to improve performance
var trails = {};
/** Cap trail SVG growth: ~10s of history at a 30 Hz regulated rate. */
var MAX_TRAIL_SEGMENTS = 300;

// Pie-slice path for one quadrant of a circle of radius r, centered at 0,0
function quadrantPath(r, startDeg, endDeg) {
  var start = (startDeg * Math.PI) / 180;
  var end = (endDeg * Math.PI) / 180;
  var x1 = r * Math.cos(start);
  var y1 = r * Math.sin(start);
  var x2 = r * Math.cos(end);
  var y2 = r * Math.sin(end);
  return `M0,0 L${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2} Z`;
}

function addOrUpdateTableRow(table, key, value) {
  var existingRow = table.querySelector(`tr[data-key="${key}"]`);
  if (existingRow) {
    var cell = existingRow.querySelector("td");
    if (cell && cell.textContent !== String(value)) {
      cell.textContent = value;
      return true;
    }
    return false;
  }
  var newRow = document.createElement("tr");
  newRow.setAttribute("data-key", key);
  newRow.innerHTML = `<th>${key}</th><td>${value}</td>`;
  table.appendChild(newRow);
  return true;
}

function tooltipNodes(mark) {
  if (!mark._tooltipTable || !mark._tooltipFo) {
    mark._tooltipTable = mark.node.querySelector(".mark-tooltip-content");
    mark._tooltipFo = mark.node.querySelector(".mark-tooltip");
  }
  return { table: mark._tooltipTable, tooltip: mark._tooltipFo };
}

function updateTooltipContent(mark, o, show_telemetry) {
  if (!show_telemetry) return;

  const persistentData = o.persistent_data;
  if (!persistentData) return;

  const { table, tooltip } = tooltipNodes(mark);
  if (!table) return;

  const persistentDataArray = Object.entries(persistentData).flatMap(
    ([key, value]) =>
      typeof value === "object" && value !== null
        ? Object.entries(value).map(([nestedKey, nestedValue]) => ({
            key: `${key}.${nestedKey}`,
            value: nestedValue,
          }))
        : { key, value },
  );

  var changed = false;
  persistentDataArray.forEach(({ key, value }) => {
    if (addOrUpdateTableRow(table, key, value)) {
      changed = true;
    }
  });

  if (tooltip && changed) {
    const { width, height } = table.getBoundingClientRect();
    tooltip.setAttribute("width", width);
    tooltip.setAttribute("height", height);
    tooltip.classList.toggle("telemetry-hide", !show_telemetry);
  }
}

function ensureTrail(svgCanvas, o) {
  var trail = trails[o.id];
  if (trail) return trail;
  trail = svgCanvas
    .group()
    .attr("id", "trail_" + o.id)
    .addClass("trail")
    .addClass(o.type);
  trails[o.id] = trail;
  return trail;
}

function appendTrailSegment(trail, prev_x, prev_y, x, y, color) {
  if (prev_x === x && prev_y === y) return;

  var line = trail.line(prev_x, prev_y, x, y);
  line.attr("stroke", color);

  var nodes = trail.node.childNodes;
  while (nodes.length > MAX_TRAIL_SEGMENTS) {
    trail.node.removeChild(nodes[0]);
  }
}

// Plot marks
function plot(
  objects,
  scale,
  scene_y_max,
  svgCanvas,
  show_telemetry,
  show_trails,
  assetMarkColors,
) {
  if (!objects || !objects.length) {
    if (Object.keys(marks).length) {
      removeExpiredMarks(new Set(Object.keys(marks)));
    }
    return;
  }

  // Diff against the previous frame so expired tracks leave the DOM.
  var oldMarks = new Set(Object.keys(marks));
  var newMarks = new Set();

  objects.forEach((o) => newMarks.add(String(o.id)));
  newMarks.forEach((o) => oldMarks.delete(o));
  removeExpiredMarks(oldMarks);

  objects.forEach((o) => {
    var mark;
    var trail;

    o.translation = metersToPixels(o.translation, scale, scene_y_max);
    var x = o.translation[0];
    var y = o.translation[1];

    if (o.id in marks) {
      mark = marks[o.id];
      if (show_trails) {
        trail = ensureTrail(svgCanvas, o);
      }
    }

    if (mark) {
      var prev_x = mark.matrix.e;
      var prev_y = mark.matrix.f;

      if (prev_x !== x || prev_y !== y) {
        mark.transform("T" + x + "," + y);
      }

      if (show_trails && trail) {
        appendTrailSegment(
          trail,
          prev_x,
          prev_y,
          x,
          y,
          mark.node.getAttribute("data-color"),
        );
      }
    } else {
      ({ mark, trail } = addNewMark(
        mark,
        o,
        trail,
        svgCanvas,
        scale,
        show_telemetry,
        show_trails,
        assetMarkColors,
      ));
    }

    if (show_telemetry) {
      updateTooltipContent(mark, o, show_telemetry);
    }
  });
}

function removeExpiredMarks(oldMarks) {
  oldMarks.forEach((o) => {
    marks[o].remove();
    delete marks[o];

    if (trails[o]) {
      trails[o].remove();
      delete trails[o];
    }
  });
}

function clearAllTrails() {
  Object.keys(trails).forEach((id) => {
    trails[id].remove();
    delete trails[id];
  });
}

function addNewMark(
  mark,
  o,
  trail,
  svgCanvas,
  scale,
  show_telemetry,
  show_trails,
  assetMarkColors,
) {
  mark = svgCanvas
    .group()
    .attr("id", "mark_" + o.id)
    .addClass("mark")
    .addClass(o.type);

  if (show_trails) {
    trail = ensureTrail(svgCanvas, o);
  }

  // FIXME: Make object size in the display a configurable option, or receive from Scenescape
  if (o.type == "person") {
    mark_radius = parseInt(scale * 0.3); // Person is about 0.3 meter radius
  } else if (o.type == "vehicle") {
    mark_radius = parseInt(scale * 1.5); // Vehicles are about 1.5 meters "radius" (3 meters across)
  } else if (o.type == "apriltag") {
    mark_radius = parseInt(scale * 0.15); // Arbitrary AprilTag size (smaller than person)
  } else {
    mark_radius = parseInt(scale * 0.5); // Everything else is 0.5 meters
  }

  // Set a color based on the ID; kept on the group so trails can reuse it
  var trackColor = "#" + o.id.substring(0, 6);
  mark.node.setAttribute("data-color", trackColor);

  // Person/vehicle cores use a 4-quadrant checkerboard (asset mark_color /
  // UUID color) so marks stay readable on both light and dark map backgrounds.
  if (o.type === "apriltag") {
    mark
      .circle(0, 0, mark_radius)
      .addClass("mark-core")
      .attr("stroke", trackColor);
  } else {
    var coreRadius = Math.max(7, Math.round(mark_radius * 0.4));
    var baseColor = (assetMarkColors && assetMarkColors[o.type]) || "black";
    var quadrantColors = [baseColor, trackColor, baseColor, trackColor];
    for (var i = 0; i < 4; i++) {
      mark
        .path(quadrantPath(coreRadius, i * 90, (i + 1) * 90))
        .addClass("mark-core")
        .attr("fill", quadrantColors[i]);
    }
  }

  // Tooltip foreignObject (only filled while Show Telemetry is on)
  var foreignObject = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "foreignObject",
  );

  foreignObject.setAttribute("width", 0);
  foreignObject.setAttribute("height", 0);
  foreignObject.setAttribute("x", 4);
  foreignObject.setAttribute("y", 4);
  foreignObject.setAttribute("class", "mark-tooltip");
  foreignObject.setAttribute("id", "tooltip_" + o.id);

  var table = document.createElement("table");
  table.className = "mark-tooltip-content";
  foreignObject.appendChild(table);

  mark.node.appendChild(foreignObject);
  mark._tooltipTable = table;
  mark._tooltipFo = foreignObject;

  if (!show_telemetry) {
    foreignObject.classList.add("telemetry-hide");
  }

  var title = Snap.parse("<title>" + o.id + "</title>");
  mark.append(title);
  if (o.type == "apriltag") {
    mark.text(0, 0, String(o.tag_id));
  }

  mark.transform("T" + o.translation[0] + "," + o.translation[1]);

  marks[o.id] = mark;

  return { mark, trail };
}

// Export methods for external use
export { plot, clearAllTrails };
