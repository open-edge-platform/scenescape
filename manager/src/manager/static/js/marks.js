// SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import { metersToPixels } from "/static/js/utils.js";

var mark_radius = 9;
var marks = {}; // Global object to store marks to improve performance
var trails = {};

function colorFromObjectId(objectId) {
  let hash = 0;
  for (let index = 0; index < objectId.length; index += 1) {
    hash = (hash * 31 + objectId.charCodeAt(index)) >>> 0;
  }
  const color = (hash & 0xffffff).toString(16).padStart(6, "0");
  return `#${color}`;
}

function createTrailGroup(svgCanvas, objectId, type, suffix, stroke) {
  return svgCanvas
    .group()
    .attr("id", `trail_${objectId}_${suffix}`)
    .addClass("trail")
    .addClass(type)
    .addClass(`trail-${suffix}`)
    .attr("stroke", stroke)
    .attr("fill", "none");
}

function ensureTrailState(
  svgCanvas,
  objectId,
  type,
  stroke,
  seedPoint = null,
) {
  let trail = trails[objectId];
  if (!trail) {
    trail = {
      observedGroup: createTrailGroup(
        svgCanvas,
        objectId,
        type,
        "observed",
        stroke,
      ),
      predictedGroup: createTrailGroup(
        svgCanvas,
        objectId,
        type,
        "predicted",
        stroke,
      ),
      lastObservedPoint: null,
      lastObservedTimestamp: null,
      lastPredictedPoint: null,
      lastRenderedPoint: null,
      predictedPath: null,
    };
    trails[objectId] = trail;
  } else {
    if (!trail.observedGroup) {
      trail.observedGroup = createTrailGroup(
        svgCanvas,
        objectId,
        type,
        "observed",
        stroke,
      );
    }
    if (!trail.predictedGroup) {
      trail.predictedGroup = createTrailGroup(
        svgCanvas,
        objectId,
        type,
        "predicted",
        stroke,
      );
    }
    trail.observedGroup.attr("stroke", stroke);
    trail.predictedGroup.attr("stroke", stroke);
  }
  if (!trail.lastObservedPoint && seedPoint) {
    trail.lastObservedPoint = seedPoint.slice();
  }
  if (!trail.lastRenderedPoint && seedPoint) {
    trail.lastRenderedPoint = seedPoint.slice();
  }
  return trail;
}

function clearPredictedTrail(trail) {
  if (!trail || !trail.predictedGroup) {
    return;
  }
  trail.predictedGroup.clear();
  trail.lastPredictedPoint = null;
  trail.predictedPath = null;
}

function appendTrailLine(group, startPoint, endPoint, stroke) {
  const line = group.line(
    startPoint[0],
    startPoint[1],
    endPoint[0],
    endPoint[1],
  );
  line.attr("stroke", stroke);
}

function appendPredictedPath(trail, startPoint, endPoint, stroke) {
  if (!trail.predictedPath) {
    trail.predictedPath = trail.predictedGroup
      .path(`M${startPoint[0]},${startPoint[1]} L${endPoint[0]},${endPoint[1]}`)
      .attr({
        stroke,
        fill: "none",
        "stroke-dasharray": "8 6",
        "stroke-linecap": "butt",
      });
    return;
  }
  trail.predictedPath.attr(
    "d",
    `${trail.predictedPath.attr("d")} L${endPoint[0]},${endPoint[1]}`,
  );
}

function updateTrail(
  trail,
  translation,
  stroke,
  positionSource,
  observationTimestamp,
) {
  const renderedStart = trail.lastRenderedPoint || trail.lastObservedPoint;
  if (positionSource === "predicted") {
    if (renderedStart && (
      !trail.lastPredictedPoint
      || trail.lastPredictedPoint[0] !== translation[0]
      || trail.lastPredictedPoint[1] !== translation[1]
      || trail.lastPredictedPoint[2] !== translation[2]
    )) {
      appendPredictedPath(trail, renderedStart, translation, stroke);
    }
    trail.lastPredictedPoint = translation.slice();
    trail.lastRenderedPoint = translation.slice();
    return;
  }

  if (trail.lastObservedPoint) {
    appendTrailLine(
      trail.observedGroup,
      trail.lastObservedPoint,
      translation,
      stroke,
    );
  }
  trail.lastObservedPoint = translation.slice();
  trail.lastObservedTimestamp = observationTimestamp || null;
  trail.lastRenderedPoint = translation.slice();
  clearPredictedTrail(trail);
}

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
function plot(
  objects,
  scale,
  scene_y_max,
  svgCanvas,
  show_telemetry,
  show_trails,
) {
  // Scenescape sends only updated marks, so we need to determine
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
    const stroke = colorFromObjectId(o.id);

    // Convert from meters to pixels
    o.translation = metersToPixels(o.translation, scale, scene_y_max);
    if (o.id in marks) {
      mark = marks[o.id];
      if (show_trails) {
        trail = ensureTrailState(
          svgCanvas,
          o.id,
          o.type,
          stroke,
          [mark.matrix.e, mark.matrix.f],
        );
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
        updateTrail(
          trail,
          o.translation.slice(),
          stroke,
          o.position_source || "observed",
          o.observation_timestamp,
        );
      }
      mark.attr("data-position-source", o.position_source || "observed");
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
        show_trails,
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
      trails[o].observedGroup?.remove();
      trails[o].predictedGroup?.remove();
      delete trails[o];
    }
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
) {
  const stroke = colorFromObjectId(o.id);
  mark = svgCanvas
    .group()
    .attr("id", "mark_" + o.id)
    .addClass("mark")
    .addClass(o.type);

  if (show_trails) {
    trail = ensureTrailState(
      svgCanvas,
      o.id,
      o.type,
      stroke,
      o.translation.slice(),
    );
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
  circle.attr("stroke", stroke);

  // Add a title element to the circle which will act as a tooltip
  var title = Snap.parse("<title>" + o.id + "</title>");
  circle.append(title);
  // Create Tag ID text for AprilTags only
  if (o.type == "apriltag") {
    var text = mark.text(0, 0, String(o.tag_id));
  }

  mark.transform("T" + o.translation[0] + "," + o.translation[1]);
  mark.attr("data-position-source", o.position_source || "observed");

  // Store the mark in the global marks object for future use
  marks[o.id] = mark;

  if (show_trails) {
    trail.lastObservedPoint =
      (o.position_source || "observed") === "predicted" ? null : o.translation.slice();
    trail.lastObservedTimestamp =
      (o.position_source || "observed") === "predicted"
        ? null
        : (o.observation_timestamp || null);
    trail.lastPredictedPoint =
      (o.position_source || "observed") === "predicted" ? o.translation.slice() : null;
    trail.lastRenderedPoint = o.translation.slice();
    trails[o.id] = trail;
  }
  return { mark, trail };
}

// Export methods for external use
export { plot };
