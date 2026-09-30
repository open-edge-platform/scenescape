// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// OSM ROI generation for scene update form.
// Two-step preview flow: generate preview, show visualization, then confirm creation.
// Row visibility (geospatial map_type only) is handled by toggleMapFields() in scene-form.js.

let cachedRois = null;

/**
 * Rotate a point around a center by the given angle (in degrees).
 */
function rotatePoint(point, center, angleDegrees) {
  const angleRad = (angleDegrees * Math.PI) / 180;
  const cos = Math.cos(angleRad);
  const sin = Math.sin(angleRad);
  const x = point[0] - center[0];
  const y = point[1] - center[1];
  return [
    center[0] + x * cos - y * sin,
    center[1] + x * sin + y * cos,
  ];
}

/**
 * Compute the centroid of all ROI points.
 */
function computeCentroid(rois) {
  let sumX = 0,
    sumY = 0,
    count = 0;
  for (const roi of rois) {
    for (const [x, y] of roi.points) {
      sumX += x;
      sumY += y;
      count++;
    }
  }
  return count > 0 ? [sumX / count, sumY / count] : [0, 0];
}

/**
 * Draw ROIs on a canvas preview with auto-scaled bounding box and colored polygons.
 * Applies map heading rotation so the preview aligns with the map orientation.
 */
function drawRoiPreview(canvas, rois, bearing = 0) {
  if (!canvas || !rois || rois.length === 0) return;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Compute rotation center (centroid of all points)
  const center = computeCentroid(rois);

  // Compute bounding box after rotation
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;

  for (const roi of rois) {
    for (const point of roi.points) {
      const rotated = rotatePoint(point, center, bearing);
      minX = Math.min(minX, rotated[0]);
      maxX = Math.max(maxX, rotated[0]);
      minY = Math.min(minY, rotated[1]);
      maxY = Math.max(maxY, rotated[1]);
    }
  }

  const padding = 10;
  const bbWidth = maxX - minX || 1;
  const bbHeight = maxY - minY || 1;
  const scaleX = (canvas.width - 2 * padding) / bbWidth;
  const scaleY = (canvas.height - 2 * padding) / bbHeight;
  const scale = Math.min(scaleX, scaleY);

  // Draw each ROI with a different color
  const colors = [
    "#FF6B6B",
    "#4ECDC4",
    "#45B7D1",
    "#FFA07A",
    "#98D8C8",
    "#F7DC6F",
    "#BB8FCE",
  ];

  for (let i = 0; i < rois.length; i++) {
    const roi = rois[i];
    const color = colors[i % colors.length];

    ctx.fillStyle = color + "40"; // 25% opacity
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;

    ctx.beginPath();
    for (let j = 0; j < roi.points.length; j++) {
      const rotated = rotatePoint(roi.points[j], center, bearing);
      const canvasX = padding + (rotated[0] - minX) * scale;
      const canvasY = padding + (rotated[1] - minY) * scale;

      if (j === 0) {
        ctx.moveTo(canvasX, canvasY);
      } else {
        ctx.lineTo(canvasX, canvasY);
      }
    }
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  // Draw border
  ctx.strokeStyle = "#333";
  ctx.lineWidth = 1;
  ctx.strokeRect(padding, padding, bbWidth * scale, bbHeight * scale);

  // Draw heading indicator (north arrow pointing up if bearing is 0)
  if (bearing !== 0) {
    const arrowX = canvas.width - 30;
    const arrowY = 30;
    ctx.save();
    ctx.translate(arrowX, arrowY);
    ctx.rotate((bearing * Math.PI) / 180);
    ctx.strokeStyle = "#999";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, -15);
    ctx.lineTo(0, 15);
    ctx.moveTo(-5, 5);
    ctx.lineTo(0, 15);
    ctx.lineTo(5, 5);
    ctx.stroke();
    ctx.restore();
  }
}

/**
 * Display ROI preview on canvas and in a list.
 */
function displayRoiPreview(rois, bearing = 0) {
  const canvas = document.getElementById("osmRoiPreviewCanvas");
  const listDiv = document.getElementById("osmRoiPreviewList");
  const previewContainer = document.getElementById("osmRoiPreviewContainer");

  if (!previewContainer) return;

  drawRoiPreview(canvas, rois, bearing);

  // Build ROI list with width information
  let listHtml = "<strong>" + rois.length + " ROI(s) to create:</strong><ul>";
  for (const roi of rois) {
    const widthStr = roi.width_m ? ` (${roi.width_m.toFixed(1)}m)` : "";
    listHtml += `<li>${roi.name}${widthStr}</li>`;
  }
  listHtml += "</ul>";
  listDiv.innerHTML = listHtml;

  previewContainer.style.display = "";
  cachedRois = rois;
}

/**
 * Hide the preview container and clear cached ROIs.
 */
function hideRoiPreview() {
  const previewContainer = document.getElementById("osmRoiPreviewContainer");
  if (previewContainer) {
    previewContainer.style.display = "none";
  }
  cachedRois = null;
}

/**
 * Generate ROI preview and display for user confirmation.
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
      hideRoiPreview();
      return;
    }

    statusDiv.innerHTML = "";
    const bearing = previewResult.bearing || 0;
    displayRoiPreview(previewResult.rois, bearing);
  } catch (error) {
    console.error("OSM ROI preview failed:", error);
    statusDiv.innerHTML =
      '<div class="alert alert-danger">' + error.message + "</div>";
    hideRoiPreview();
  }
}

/**
 * Create the ROIs that were previewed.
 */
async function confirmCreateRois() {
  if (!cachedRois || cachedRois.length === 0) {
    alert("No ROIs to create");
    return;
  }

  const statusDiv = document.getElementById("osmRoiStatus");
  const sceneUID = document.getElementById("sceneUID");

  statusDiv.innerHTML =
    '<div class="alert alert-info">Creating ROIs...</div>';

  try {
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
    if (!csrfToken) {
      throw new Error("CSRF token not found");
    }

    // Force all ROIs to be created
    const allRois = cachedRois.map((roi) => ({ ...roi, checked: true }));

    const createResponse = await fetch(
      "/api/v1/create-selected-rois-from-osm/",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken.value,
        },
        body: JSON.stringify({
          scene: sceneUID.value,
          rois: allRois,
        }),
      }
    );

    const createResult = await createResponse.json();
    if (!createResponse.ok) {
      throw new Error(
        createResult.error || `Create failed (${createResponse.status})`
      );
    }

    const summary = createResult.created
      .map((roi) => `• ${roi.name}`)
      .join("<br>");
    statusDiv.innerHTML =
      '<div class="alert alert-success">' +
      createResult.created.length +
      " ROI(s) created:<br>" +
      summary +
      "</div>";
    hideRoiPreview();
  } catch (error) {
    console.error("OSM ROI creation failed:", error);
    statusDiv.innerHTML =
      '<div class="alert alert-danger">' + error.message + "</div>";
  }
}

/**
 * Cancel the ROI creation and hide the preview.
 */
function cancelCreateRois() {
  hideRoiPreview();
  const statusDiv = document.getElementById("osmRoiStatus");
  if (statusDiv) {
    statusDiv.innerHTML = "";
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const generateBtn = document.getElementById("generateRoisBtn");
  const confirmBtn = document.getElementById("confirmCreateRoisBtn");
  const cancelBtn = document.getElementById("cancelCreateRoisBtn");

  if (generateBtn) {
    generateBtn.addEventListener("click", generateRoisFromOsm);
  }
  if (confirmBtn) {
    confirmBtn.addEventListener("click", confirmCreateRois);
  }
  if (cancelBtn) {
    cancelBtn.addEventListener("click", cancelCreateRois);
  }
});
