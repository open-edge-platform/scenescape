// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import { metersToPixels } from "/static/js/utils.js";

var mark_radius = 9;
var marks = {}; // Global object to store marks to improve performance
var trails = {};
var show_trails = false;

function addOrUpdateTableRow(table, key, value) {
  var existingRow = table.querySelector(`tr[data-key="${key}"]`);
  if (existingRow) {
    existingRow.querySelector("td").textContent = value;
  } else {
    var newRow = document.createElement("tr");
    newRow.setAttribute("data-key", key);
    newRow.innerHTML = `<th>${key}</th><td>${value}</td>`;
    table.appendChild(newRow);
  }
}

function updateTooltipContent(mark, o, show_telemetry) {
  const table = mark.node.querySelector(".mark-tooltip-content");
  const tooltip = mark.node.querySelector(".mark-tooltip");
  const persistentData = o.persistent_data;

  if (!persistentData) return;

  const persistentDataArray = Object.entries(persistentData).flatMap(
    ([key, value]) =>
      typeof value === "object" && value !== null
        ? Object.entries(value).map(([nestedKey, nestedValue]) => ({
            key: `${key}.${nestedKey}`,
            value: nestedValue,
          }))
        : { key, value },
  );

  persistentDataArray.forEach(({ key, value }) =>
    addOrUpdateTableRow(table, key, value),
  );

  if (tooltip) {
    const { width, height } = table.getBoundingClientRect();
    tooltip.setAttribute("width", width);
    tooltip.setAttribute("height", height);
    tooltip.classList.toggle("telemetry-hide", !show_telemetry);
  }
}

// Plot marks
function plot(objects, scale, scene_y_max, svgCanvas, show_telemetry) {
  // SceneScape sends only updated marks, so we need to determine
  // which old marks are not in the current update and remove them

  // Create a set based on the current keys (object IDs) of the global
  // marks object
  var oldMarks = new Set(Object.keys(marks));
  var newMarks = new Set();

  // Add new marks from the current message into the newMarks set
  objects.forEach((o) => newMarks.add(String(o.id)));

  // Remove any newMarks from oldMarks, leaving only expired marks
  newMarks.forEach((o) => oldMarks.delete(o));

  // Remove oldMarks from both the DOM and the global marks object
  removeExpiredMarks(oldMarks);

  // Plot each object in the message
  objects.forEach((o) => {
    var mark;
    var trail;

    // Convert from meters to pixels
    o.translation = metersToPixels(o.translation, scale, scene_y_max);

    if (o.id in marks) {
      mark = marks[o.id];
      if (show_trails) {
        trail = trails[o.id];
      }
    }

    // Update mark if it already exists
    if (mark) {
      var prev_x = mark.matrix.e;
      var prev_y = mark.matrix.f;

      mark.transform("T" + o.translation[0] + "," + o.translation[1]);
      // Update the title element (tooltip) with the new o.id
      var title = mark.select("title");
      if (!title) {
        // If a title element does not exist, create one and append it to the mark
        title = Snap.parse("<title>" + o.id + "</title>");
        mark.append(title);
      }
      // Update the text of the existing title element with the new o.id
      title.node.textContent = o.id;

      // Add a new line segment to the trail if enabled
      if (show_trails && trail) {
        var line = trail.line(
          prev_x,
          prev_y,
          o.translation[0],
          o.translation[1],
        );
        line.attr("stroke", mark.select("circle").attr("stroke"));
      }
    }
    // Otherwise, add new mark
    else {
      ({ mark, trail } = addNewMark(
        mark,
        o,
        trail,
        svgCanvas,
        scale,
        show_telemetry,
      ));
    }
    updateTooltipContent(mark, o, show_telemetry);
  });
}

function removeExpiredMarks(oldMarks) {
  oldMarks.forEach((o) => {
    marks[o].remove(); // Remove from DOM
    delete marks[o]; // Delete from the marks object

    // Also remove old trails
    if (trails[o]) {
      trails[o].remove();
      delete trails[o];
    }
  });
}

function addNewMark(mark, o, trail, svgCanvas, scale, show_telemetry) {
  mark = svgCanvas
    .group()
    .attr("id", "mark_" + o.id)
    .addClass("mark")
    .addClass(o.type);

  if (show_trails) {
    trail = svgCanvas
      .group()
      .attr("id", "mark_" + o.id)
      .addClass("trail")
      .addClass(o.type);
  }

  // FIXME: Make object size in the display a configurable option, or receive from SceneScape
  if (o.type == "person") {
    mark_radius = parseInt(scale * 0.3); // Person is about 0.3 meter radius
  } else if (o.type == "vehicle") {
    mark_radius = parseInt(scale * 1.5); // Vehicles are about 1.5 meters "radius" (3 meters across)
  } else if (o.type == "apriltag") {
    mark_radius = parseInt(scale * 0.15); // Arbitrary AprilTag size (smaller than person)
  } else {
    mark_radius = parseInt(scale * 0.5); // Everything else is 0.5 meters
  }

  // Create the circle
  var circle = mark.circle(0, 0, mark_radius);

  // add tooltip foreign object
  var text = mark.text(0, 0, "");
  var foreignObject = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "foreignObject",
  );

  foreignObject.setAttribute("width", 0); // Outer container width
  foreignObject.setAttribute("height", 0); // Outer container height
  foreignObject.setAttribute("x", 4);
  foreignObject.setAttribute("y", 4);
  foreignObject.setAttribute("class", "mark-tooltip");
  foreignObject.setAttribute("id", "tooltip_" + o.id);

  var table = document.createElement("table");
  table.className = "mark-tooltip-content";
  foreignObject.appendChild(table);

  mark.node.appendChild(foreignObject);

  if (!show_telemetry) {
    foreignObject.classList.add("telemetry-hide");
  }

  // Set a stroke color based on the ID
  circle.attr("stroke", "#" + o.id.substring(0, 6));

  // Add a title element to the circle which will act as a tooltip
  var title = Snap.parse("<title>" + o.id + "</title>");
  circle.append(title);
  // Create Tag ID text for AprilTags only
  if (o.type == "apriltag") {
    var text = mark.text(0, 0, String(o.tag_id));
  }

  mark.transform("T" + o.translation[0] + "," + o.translation[1]);

  // Store the mark in the global marks object for future use
  marks[o.id] = mark;

  if (show_trails) {
    trails[o.id] = trail;
  }
  return { mark, trail };
}

// Export methods for external use
export { plot };
