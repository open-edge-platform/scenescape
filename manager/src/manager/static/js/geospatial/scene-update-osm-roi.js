// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * OSM ROI generation for Regions tab.
 * 
 * Fetches OSM-derived ROIs via the PreviewRoisFromOsm endpoint and draws them directly
 * on the main 2D canvas as "proposed" regions (dashed outline, OSM badge).
 * 
 * The user can then edit these regions using the same tools as manual ROIs:
 * - Drag vertices to adjust boundaries
 * - Double-click to enter/exit edit mode
 * - Right-click a vertex to remove that point
 * - Double right-click a polygon/region to delete the entire region
 * - Save via the "Save Regions and Tripwires" button
 * 
 * All OSM-generated and manual regions are persisted together through the standard
 * form submission flow (stringifyRois → #id_rois JSON).
 */

import { drawRoi, numberRois, stringifyRois, getSelectionBoundsMeters, clearSelectionArea } from '../sscape.js';

/**
 * Cuts a simple polygon down to the part that falls inside an axis-aligned
 * rectangle (Sutherland-Hodgman clipping, one pass per rectangle edge).
 * Only used to fit auto-generated OSM ROIs to a selection box, not a general tool.
 */
function clipPolygonToBounds(points, bounds) {
  const planes = [
    { inside: (p) => p[0] >= bounds.minX, axis: 0, value: bounds.minX },
    { inside: (p) => p[0] <= bounds.maxX, axis: 0, value: bounds.maxX },
    { inside: (p) => p[1] >= bounds.minY, axis: 1, value: bounds.minY },
    { inside: (p) => p[1] <= bounds.maxY, axis: 1, value: bounds.maxY },
  ];

  return planes.reduce((poly, plane) => {
    if (poly.length === 0) return poly;
    const output = [];
    for (let i = 0; i < poly.length; i++) {
      const current = poly[i];
      const prev = poly[(i + poly.length - 1) % poly.length];
      const currentIn = plane.inside(current);
      const prevIn = plane.inside(prev);
      if (currentIn !== prevIn) {
        const other = plane.axis === 0 ? 1 : 0;
        const t = (plane.value - prev[plane.axis]) / (current[plane.axis] - prev[plane.axis]);
        const point = [];
        point[plane.axis] = plane.value;
        point[other] = prev[other] + t * (current[other] - prev[other]);
        output.push(point);
      }
      if (currentIn) output.push(current);
    }
    return output;
  }, points);
}

/**
 * Generate OSM ROI previews and draw them on the main canvas.
 * 
 * Called when user clicks "Create ROIs from OSM" button.
 */
async function generateRoisFromOsm() {
  const statusDiv = document.getElementById("osmRoiStatus");
  const sceneUID = document.getElementById("sceneUID");

  if (!statusDiv || !sceneUID || !sceneUID.value) {
    if (statusDiv) {
      statusDiv.innerHTML =
        '<div class="alert alert-danger">Scene ID not found</div>';
    }
    return;
  }

  statusDiv.innerHTML =
    '<div class="alert alert-info">Generating ROI preview...</div>';

  try {
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
    if (!csrfToken) {
      throw new Error("CSRF token not found");
    }

    const previewResponse = await fetch("/api/v1/preview-rois-from-osm/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken.value,
      },
      body: JSON.stringify({
        scene: sceneUID.value,
      }),
    });

    const previewResult = await previewResponse.json();
    if (!previewResponse.ok) {
      throw new Error(
        previewResult.error || `Preview failed (${previewResponse.status})`
      );
    }

    if (!previewResult.rois || previewResult.rois.length === 0) {
      statusDiv.innerHTML =
        '<div class="alert alert-warning">No OSM ROIs found in the bounding box.</div>';
      return;
    }

    // If the user dragged out a selection area, cut each ROI polygon down to just
    // the part that falls inside it, instead of showing the full, uncut road shape.
    const selectionBounds = getSelectionBoundsMeters();
    let rois = previewResult.rois;
    if (selectionBounds) {
      rois = rois
        .map((roi) => ({
          ...roi,
          points: clipPolygonToBounds(roi.points, selectionBounds),
        }))
        .filter((roi) => roi.points.length >= 3);
    }

    if (rois.length === 0) {
      statusDiv.innerHTML =
        '<div class="alert alert-warning">No OSM ROIs found in the selected area.</div>';
      return;
    }

    // Draw each OSM-derived ROI on the main canvas as a proposed region
    for (const roi of rois) {
      // Shape the ROI preview like a saved region object
      const regionEntry = {
        points: roi.points,
        title: roi.name,  // drawRoi expects 'title', not 'name'
        uuid: roi.uuid,
        volumetric: false,
        height: 0,
        buffer_size: 0,  // drawRoi expects 'buffer_size', not 'buffer'
        sectors: { thresholds: {}, range_max: 0 },  // drawRoi expects this structure; empty since OSM ROIs don't have occupancy data
        tags: roi.tags || {},
        width_m: roi.width_m,
        type: roi.type,  // OSM way type (e.g., "footway", "secondary", "pedestrian")
        osm_derived: true, // Flag to add OSM badge in form row
      };

      // Draw on main canvas using the standard drawRoi function
      // Pass "osm_proposed" as type to signal this should be styled as proposed
      drawRoi(regionEntry, roi.uuid, "roi");

      // Mark the SVG group with osm_derived flag for later serialization
      const svgGroup = Snap.select(`#roi_${roi.uuid}`);
      if (svgGroup) {
        svgGroup.data("osm_derived", true);
      }

      // Mark the newly created region row with .proposed-roi class
      const regionRow = document.getElementById(`form-roi_${roi.uuid}`);
      if (regionRow) {
        regionRow.classList.add("proposed-roi");
        
        // Add OSM badge if not already present
        const titleInput = regionRow.querySelector(".roi-title");
        if (titleInput && !regionRow.querySelector(".osm-badge")) {
          const badge = document.createElement("span");
          badge.className = "osm-badge";
          badge.textContent = "OSM";
          badge.title = "This region was generated from OpenStreetMap data";
          titleInput.parentElement.appendChild(badge);
        }
      }

      // Mark the SVG group with proposed-roi styling
      const svgPolygon = Snap.select(`#roi_${roi.uuid} polygon`);
      if (svgPolygon) {
        svgPolygon.parent().addClass("proposed-roi");
      }
    }

    // Update region numbering and trigger canvas update
    numberRois();
    stringifyRois();
    if (selectionBounds) clearSelectionArea();

    statusDiv.innerHTML =
      '<div class="alert alert-success">' +
      rois.length +
      ' OSM ROI(s) added to canvas. Drag vertices to adjust, then save.</div>';
  } catch (error) {
    console.error("OSM ROI preview failed:", error);
    const alertDiv = document.createElement("div");
    alertDiv.className = "alert alert-danger";
    // Use textContent (not innerHTML) to safely render error message as plain text,
    // preventing XSS injection if upstream API returns malicious content.
    alertDiv.textContent = error.message;
    statusDiv.innerHTML = "";
    statusDiv.appendChild(alertDiv);
  }
}

// Attach event handler on page load
document.addEventListener("DOMContentLoaded", function () {
  const generateBtn = document.getElementById("generateRoisBtn");
  if (generateBtn) {
    generateBtn.addEventListener("click", generateRoisFromOsm);
  }
});
