// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// "Select Area" tool state: a rectangle dragged on the map that scopes ROI deletion and OSM suggestions.

import { pixelsToMeters } from "/static/js/utils.js";

// True while the user is actively dragging out a new selection-area rectangle
var selectingArea = false;
// Pixel coords of the drag's starting corner, while selectingArea is true
var selectionDragStart = null;
// The <rect> currently shown for the selection area, or null if none
var selectionRectEl = null;
// {minX, minY, maxX, maxY} in canvas pixels for the current selection area, or null
var selectionBoundsPx = null;

function cursorPoint(e) {
  var offset = $("#svgout").offset();
  return [parseInt(e.pageX - offset.left), parseInt(e.pageY - offset.top)];
}

/** Arm the tool so the next drag on the canvas draws a new selection rectangle. */
function beginSelectArea() {
  clearSelectionArea();
  $("#svgout").addClass("selecting-area");
  selectingArea = true;
}

/** Disarm the tool, remove the selection-area rectangle (if any) and forget its bounds. */
function clearSelectionArea() {
  if (selectionRectEl) {
    selectionRectEl.remove();
    selectionRectEl = null;
  }
  selectingArea = false;
  selectionDragStart = null;
  $("#svgout").removeClass("selecting-area");
  selectionBoundsPx = null;
  updateSelectAreaButton();
}

/** Highlights the "Select Area" button while a selection box is active, grey otherwise. */
function updateSelectAreaButton() {
  $("#select-roi-area")
    .toggleClass("btn-primary", !!selectionBoundsPx)
    .toggleClass("btn-secondary", !selectionBoundsPx);
}

/** Current selection in canvas pixels, or null if none is active. */
function getSelectionBoundsPx() {
  return selectionBoundsPx;
}

/** Current selection converted to scene-local meters, or null if none is active. */
function selectionBoundsToMeters(scale, sceneYMax) {
  if (!selectionBoundsPx) return null;

  var b = selectionBoundsPx;
  var p1 = pixelsToMeters([b.minX, b.minY], scale, sceneYMax);
  var p2 = pixelsToMeters([b.maxX, b.maxY], scale, sceneYMax);

  return {
    minX: Math.min(p1[0], p2[0]),
    maxX: Math.max(p1[0], p2[0]),
    minY: Math.min(p1[1], p2[1]),
    maxY: Math.max(p1[1], p2[1]),
  };
}

function selectionMouseDown(svgCanvas, e) {
  if (!selectingArea) return;

  selectionDragStart = cursorPoint(e);
  if (selectionRectEl) selectionRectEl.remove();
  selectionRectEl = svgCanvas
    .rect(selectionDragStart[0], selectionDragStart[1], 0, 0)
    .addClass("roi-selection-box");
}

function selectionMouseMove(e) {
  if (!selectingArea || !selectionDragStart || !selectionRectEl) return;

  var current = cursorPoint(e);
  selectionRectEl.attr({
    x: Math.min(current[0], selectionDragStart[0]),
    y: Math.min(current[1], selectionDragStart[1]),
    width: Math.abs(current[0] - selectionDragStart[0]),
    height: Math.abs(current[1] - selectionDragStart[1]),
  });
}

/** Finish a selection drag. Returns true if the event belonged to the tool. */
function selectionMouseUp(e, dragSlopPx) {
  if (!selectingArea || !selectionDragStart) return false;

  var current = cursorPoint(e);
  selectionBoundsPx = {
    minX: Math.min(current[0], selectionDragStart[0]),
    minY: Math.min(current[1], selectionDragStart[1]),
    maxX: Math.max(current[0], selectionDragStart[0]),
    maxY: Math.max(current[1], selectionDragStart[1]),
  };
  selectionDragStart = null;
  $("#svgout").removeClass("selecting-area");
  selectingArea = false;

  // Treat a near-zero-size drag (a click) as "no selection"
  if (
    selectionBoundsPx.maxX - selectionBoundsPx.minX < dragSlopPx &&
    selectionBoundsPx.maxY - selectionBoundsPx.minY < dragSlopPx
  ) {
    clearSelectionArea();
  } else {
    updateSelectAreaButton();
  }
  return true;
}

export {
  beginSelectArea,
  clearSelectionArea,
  getSelectionBoundsPx,
  selectionBoundsToMeters,
  selectionMouseDown,
  selectionMouseMove,
  selectionMouseUp,
};
