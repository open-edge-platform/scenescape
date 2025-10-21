// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// WebSocket connection for real-time updates
const socket = io();

// Canvas and visualization variables
let canvas, ctx;
let viewOffset = { x: 0, y: 0 };
let zoomLevel = 0.8; // Start with a better zoom level for meter coordinates
let isDragging = false;
let lastMousePos = { x: 0, y: 0 };

// Data storage
let currentScene = null;
let sceneData = {
  objects: [],
  clusters: [],
  metadata: {},
};
let hasAutoFittedScene = false; // Track if we've auto-fitted the current scene

// Color palettes for different object categories
const categoryColors = {
  person: "#3498db", // Blue
  vehicle: "#e74c3c", // Red
  bicycle: "#f39c12", // Orange
  motorcycle: "#9b59b6", // Purple
  truck: "#e67e22", // Dark Orange
  bus: "#1abc9c", // Turquoise
  car: "#e74c3c", // Red (same as vehicle)
  default: "#95a5a6", // Gray
};

// Cluster colors (cycling through a palette)
const clusterColors = [
  "#ff6b6b",
  "#4ecdc4",
  "#45b7d1",
  "#f9ca24",
  "#6c5ce7",
  "#fd79a8",
  "#00b894",
  "#0984e3",
  "#fdcb6e",
  "#a29bfe",
];

// Initialize the application
document.addEventListener("DOMContentLoaded", function () {
  initCanvas();
  initControls();
  initWebSocket();

  // Start the animation loop
  requestAnimationFrame(animate);
});

// Function to calculate responsive font size for canvas rendering
function getResponsiveFontSize(baseSize) {
  const dpr = window.devicePixelRatio || 1;
  const screenWidth = window.innerWidth;

  // Scale factor based on screen width and device pixel ratio
  let scaleFactor = 1;

  if (screenWidth < 480) {
    scaleFactor = 0.8;
  } else if (screenWidth < 768) {
    scaleFactor = 0.9;
  } else if (screenWidth > 1440) {
    scaleFactor = 1.2;
  }

  return Math.max(10, baseSize * scaleFactor * Math.min(dpr, 2));
}

function initCanvas() {
  canvas = document.getElementById("visualizationCanvas");
  ctx = canvas.getContext("2d");

  // Set canvas size
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);

  // Mouse event handlers
  canvas.addEventListener("mousedown", onMouseDown);
  canvas.addEventListener("mousemove", onMouseMove);
  canvas.addEventListener("mouseup", onMouseUp);
  canvas.addEventListener("wheel", onWheel);
  canvas.addEventListener("mouseleave", onMouseLeave);
}

function resizeCanvas() {
  const container = canvas.parentElement;
  canvas.width = container.clientWidth;
  canvas.height = container.clientHeight;
  draw();
}

function initControls() {
  const sceneSelect = document.getElementById("sceneSelect");
  const zoomIn = document.getElementById("zoomIn");
  const zoomOut = document.getElementById("zoomOut");
  const zoomReset = document.getElementById("zoomReset");

  // Scene selection
  sceneSelect.addEventListener("change", function () {
    const selectedScene = this.value;
    if (selectedScene && selectedScene !== currentScene) {
      selectScene(selectedScene);
    }
  });

  // Zoom controls
  zoomIn.addEventListener("click", () => zoom(1.2));
  zoomOut.addEventListener("click", () => zoom(0.8));
  zoomReset.addEventListener("click", resetView);
}

function initWebSocket() {
  const wsStatus = document.getElementById("wsStatus");
  const connectionStatus = document.getElementById("connectionStatus");

  socket.on("connect", function () {
    wsStatus.textContent = "Connected";
    wsStatus.className = "connection-status connected";
    connectionStatus.textContent = "Connected to server";
    console.log("Connected to WebSocket server");
  });

  socket.on("disconnect", function () {
    wsStatus.textContent = "Disconnected";
    wsStatus.className = "connection-status disconnected";
    connectionStatus.textContent = "Disconnected from server";
    console.log("Disconnected from WebSocket server");
  });

  socket.on("available_scenes", function (scenes) {
    updateSceneList(scenes);
  });

  socket.on("scene_data", function (data) {
    updateSceneData(data);
  });

  socket.on("clusters_update", function (data) {
    updateClusters(data);
  });
}

function updateSceneList(scenes) {
  const sceneSelect = document.getElementById("sceneSelect");
  const currentValue = sceneSelect.value;

  // Clear existing options (except the first placeholder)
  while (sceneSelect.children.length > 1) {
    sceneSelect.removeChild(sceneSelect.lastChild);
  }

  // Add scene options with names
  scenes.forEach((scene) => {
    const option = document.createElement("option");
    option.value = scene.id;
    option.textContent = scene.name || scene.id; // Use name if available, fallback to ID
    sceneSelect.appendChild(option);
  });

  // Restore selection if it still exists
  const sceneIds = scenes.map((scene) => scene.id);
  if (sceneIds.includes(currentValue)) {
    sceneSelect.value = currentValue;
  }
}

function selectScene(sceneId) {
  currentScene = sceneId;
  hasAutoFittedScene = false; // Reset auto-fit flag for new scene
  socket.emit("select_scene", { scene_id: sceneId });

  // Clear current data
  sceneData = { objects: [], clusters: [], metadata: {} };
  updateUI();
}

function updateSceneData(data) {
  if (data.scene_id === currentScene) {
    sceneData = data.data;
    updateUI();
    draw();
  }
}

function updateClusters(data) {
  if (data.scene_id === currentScene) {
    sceneData.clusters = data.clusters;
    updateUI();
    draw();
  }
}

function updateUI() {
  // Update stats
  document.getElementById("objectCount").textContent =
    sceneData.objects?.length || 0;
  document.getElementById("clusterCount").textContent =
    sceneData.clusters?.length || 0;

  if (sceneData.metadata?.timestamp) {
    const time = new Date(
      sceneData.metadata.timestamp * 1000,
    ).toLocaleTimeString();
    document.getElementById("lastUpdate").textContent = time;
  }

  // Update legend
  updateObjectLegend();
  updateClusterLegend();
  updateSceneInfo();
}

function updateObjectLegend() {
  const container = document.getElementById("objectLegend");
  container.innerHTML = "";

  if (!sceneData.objects || sceneData.objects.length === 0) {
    container.innerHTML = '<div class="no-data">No objects detected</div>';
    return;
  }

  // Count objects by category
  const categoryCounts = {};
  sceneData.objects.forEach((obj) => {
    const category = obj.category || "unknown";
    categoryCounts[category] = (categoryCounts[category] || 0) + 1;
  });

  // Create legend items
  Object.entries(categoryCounts).forEach(([category, count]) => {
    const item = document.createElement("div");
    item.className = "legend-item";

    const color = categoryColors[category] || categoryColors.default;
    item.innerHTML = `
            <div class="legend-color" style="background-color: ${color}"></div>
            ${category}: ${count}
        `;
    container.appendChild(item);
  });
}

function updateClusterLegend() {
  const container = document.getElementById("clusterLegend");
  container.innerHTML = "";

  if (!sceneData.clusters || sceneData.clusters.length === 0) {
    container.innerHTML = '<div class="no-data">No clusters found</div>';
    return;
  }

  sceneData.clusters.forEach((cluster, index) => {
    const color = clusterColors[index % clusterColors.length];
    const movementType = cluster.velocity_analysis?.movement_type || "unknown";
    const shape = cluster.shape_analysis?.shape || "unknown";

    const clusterDiv = document.createElement("div");
    clusterDiv.className = "cluster-info";
    clusterDiv.innerHTML = `
            <div class="legend-item">
                <div class="legend-color" style="background-color: ${color}"></div>
                <strong>Cluster ${index + 1}</strong>
            </div>
            <div style="margin-left: 24px; font-size: 12px; line-height: 1.4;">
                <div style="margin-bottom: 4px;"><strong>Objects:</strong> ${cluster.objects_in_cluster || 0}</div>
                <div style="margin-bottom: 4px;"><strong>Category:</strong> ${cluster.category || "mixed"}</div>
                <div style="margin-bottom: 4px;"><strong>Shape:</strong> ${shape}</div>
                <div style="color: #e67e22;"><strong>Movement:</strong> ${movementType}</div>
            </div>
        `;
    container.appendChild(clusterDiv);
  });
}

// Escapes &, <, >, ", and ' for HTML insertion
function escapeHTML(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function updateSceneInfo() {
  const container = document.getElementById("sceneInfo");

  if (!currentScene || !sceneData.metadata) {
    container.innerHTML = '<div class="no-data">No scene selected</div>';
    return;
  }

  const sceneName = sceneData.metadata.name || "Unknown Scene";
  const objectCount = sceneData.metadata.object_count || 0;

  container.innerHTML = `
        <div style="background-color: #e8f4fd; padding: 12px; border-radius: 6px; border-left: 4px solid #3498db;">
            <div style="font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 8px;">
                ${escapeHTML(sceneName)}
            </div>
            <div style="font-size: 12px; line-height: 1.4;">
                <div style="margin-bottom: 4px;"><strong>Scene ID:</strong> ${escapeHTML(currentScene)}</div>
                <div><strong>Total Objects:</strong> ${escapeHTML(objectCount)}</div>
            </div>
        </div>
    `;
}

// Canvas drawing functions
function draw() {
  if (!canvas || !ctx) return;

  // Clear canvas
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Auto-center and scale to fit all objects (only on first appearance)
  if (!hasAutoFittedScene && (sceneData.objects?.length > 0 || sceneData.clusters?.length > 0)) {
    autoFitView();
    hasAutoFittedScene = true;
  }

  // Save context for transformations
  ctx.save();

  // Apply zoom and pan transformations
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.scale(zoomLevel, zoomLevel);
  ctx.translate(viewOffset.x, viewOffset.y);

  // Draw grid (no axes)
  drawGrid();

  // Draw objects
  if (sceneData.objects) {
    drawObjects();
  }

  // Draw clusters
  if (sceneData.clusters) {
    drawClusters();
  }

  // Restore context
  ctx.restore();
}

function autoFitView() {
  const metersToPixels = 100;
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;
  let hasObjects = false;

  // Find bounds of all objects
  if (sceneData.objects && sceneData.objects.length > 0) {
    sceneData.objects.forEach((obj) => {
      const coords = getObjectCoordinates(obj);
      if (coords) {
        const pixelX = coords.x * metersToPixels;
        const pixelY = coords.y * metersToPixels;
        
        minX = Math.min(minX, pixelX);
        maxX = Math.max(maxX, pixelX);
        minY = Math.min(minY, pixelY);
        maxY = Math.max(maxY, pixelY);
        hasObjects = true;
      }
    });
  }

  // Include cluster centers in bounds
  if (sceneData.clusters && sceneData.clusters.length > 0) {
    sceneData.clusters.forEach((cluster) => {
      if (cluster.cluster_center && 
          cluster.cluster_center.x !== undefined && 
          cluster.cluster_center.y !== undefined) {
        const centerX = cluster.cluster_center.x * metersToPixels;
        const centerY = cluster.cluster_center.y * metersToPixels;
        
        minX = Math.min(minX, centerX);
        maxX = Math.max(maxX, centerX);
        minY = Math.min(minY, centerY);
        maxY = Math.max(maxY, centerY);
        hasObjects = true;
      }
    });
  }

  // If we have objects, center the view
  if (hasObjects && isFinite(minX) && isFinite(maxX) && isFinite(minY) && isFinite(maxY)) {
    // Calculate center point
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    
    // Calculate required zoom to fit all objects with some padding
    const objectsWidth = Math.max(maxX - minX, 100); // Minimum 100px width
    const objectsHeight = Math.max(maxY - minY, 100); // Minimum 100px height
    const padding = 100; // 100px padding
    
    const scaleX = (canvas.width - padding * 2) / objectsWidth;
    const scaleY = (canvas.height - padding * 2) / objectsHeight;
    const optimalZoom = Math.min(scaleX, scaleY, 2.0); // Max zoom of 2.0
    
    // Only update if this is significantly different from current view
    const currentCenterX = -viewOffset.x;
    const currentCenterY = -viewOffset.y;
    const centerThreshold = 50; // pixels
    const zoomThreshold = 0.2;
    
    if (Math.abs(currentCenterX - centerX) > centerThreshold ||
        Math.abs(currentCenterY - centerY) > centerThreshold ||
        Math.abs(zoomLevel - optimalZoom) > zoomThreshold) {
      
      // Set new view offset (negative because we're translating the canvas)
      viewOffset.x = -centerX;
      viewOffset.y = centerY; // Positive because Y is flipped
      zoomLevel = Math.max(0.1, Math.min(optimalZoom, 5.0));
    }
  }
}

function drawGrid() {
  // Scale factor to convert meters to pixels for better visualization
  // Using 100 pixels per meter for good readability
  const metersToPixels = 100;
  const gridSpacingMeters = 0.5; // Grid lines every 0.5 meters
  const gridSpacing = gridSpacingMeters * metersToPixels;
  const majorGridSpacingMeters = 1.0; // Major grid lines every 1 meter
  const majorGridSpacing = majorGridSpacingMeters * metersToPixels;

  // Calculate grid bounds - infinite-like grid that covers much larger area
  const canvasWidth = canvas.width / zoomLevel;
  const canvasHeight = canvas.height / zoomLevel;
  const gridExtent = Math.max(canvasWidth, canvasHeight) * 2; // Make grid 2x larger than canvas
  const gridStartX = -gridExtent - Math.abs(viewOffset.x * zoomLevel);
  const gridEndX = gridExtent + Math.abs(viewOffset.x * zoomLevel);
  const gridStartY = -gridExtent - Math.abs(viewOffset.y * zoomLevel);
  const gridEndY = gridExtent + Math.abs(viewOffset.y * zoomLevel);

  // Minor grid lines (0.5m spacing)
  ctx.strokeStyle = "rgba(255, 255, 255, 0.1)"; // Increased opacity from 0.05 to 0.1
  ctx.lineWidth = 1;
  
  // Vertical minor grid lines
  for (let x = Math.floor(gridStartX / gridSpacing) * gridSpacing; x <= gridEndX; x += gridSpacing) {
    ctx.beginPath();
    ctx.moveTo(x, gridStartY);
    ctx.lineTo(x, gridEndY);
    ctx.stroke();
  }
  
  // Horizontal minor grid lines
  for (let y = Math.floor(gridStartY / gridSpacing) * gridSpacing; y <= gridEndY; y += gridSpacing) {
    ctx.beginPath();
    ctx.moveTo(gridStartX, y);
    ctx.lineTo(gridEndX, y);
    ctx.stroke();
  }

  // Major grid lines (1m spacing) with subtle labels
  ctx.strokeStyle = "rgba(255, 255, 255, 0.2)"; // Increased opacity from 0.1 to 0.2
  ctx.lineWidth = 1;
  ctx.fillStyle = "rgba(255, 255, 255, 0.4)"; // Increased label opacity from 0.3 to 0.4
  const labelFontSize = getResponsiveFontSize(8);
  ctx.font = `${labelFontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`;
  ctx.textAlign = "center";

  // Vertical major grid lines with labels
  for (let x = Math.floor(gridStartX / majorGridSpacing) * majorGridSpacing; x <= gridEndX; x += majorGridSpacing) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.2)"; // Match the increased opacity
    ctx.beginPath();
    ctx.moveTo(x, gridStartY);
    ctx.lineTo(x, gridEndY);
    ctx.stroke();

    // Add labels for positive values and zero (but limit labels to visible area)
    const meterValue = x / metersToPixels;
    if (meterValue >= 0 && meterValue % 1 === 0 && meterValue <= 50) { // Only show labels up to 50m for clarity
      ctx.fillText(`${meterValue.toFixed(0)}m`, x, gridStartY + 15);
    }
  }

  // Horizontal major grid lines with labels
  for (let y = Math.floor(gridStartY / majorGridSpacing) * majorGridSpacing; y <= gridEndY; y += majorGridSpacing) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.2)"; // Match the increased opacity
    ctx.beginPath();
    ctx.moveTo(gridStartX, y);
    ctx.lineTo(gridEndX, y);
    ctx.stroke();

    // Add labels for positive values and zero (but limit labels to visible area)
    const meterValue = -y / metersToPixels; // Negative because Y is flipped
    if (meterValue >= 0 && meterValue % 1 === 0 && meterValue <= 50) { // Only show labels up to 50m for clarity
      ctx.save();
      ctx.textAlign = "right";
      ctx.fillText(`${meterValue.toFixed(0)}m`, gridStartX - 5, y + 3);
      ctx.restore();
    }
  }
}

function drawObjects() {
  // Scale factor to convert meters to pixels for visualization
  const metersToPixels = 100;
  
  sceneData.objects.forEach((obj) => {
    const coords = getObjectCoordinates(obj);
    if (coords) {
      // Convert meter coordinates to pixel coordinates
      const pixelX = coords.x * metersToPixels;
      const pixelY = coords.y * metersToPixels;
      
      // Determine object color based on cluster assignment
      let color = categoryColors.default; // Default gray for unclustered objects
      let clusterId = -1;
      
      // Try different ways to find cluster assignment
      if (obj.cluster_id !== undefined && obj.cluster_id > 0) {
        // Direct cluster_id field
        clusterId = obj.cluster_id - 1; // Convert to 0-based index
      } else if (obj.cluster !== undefined && obj.cluster > 0) {
        // Alternative cluster field
        clusterId = obj.cluster - 1;
      } else if (sceneData.clusters) {
        // Find which cluster this object belongs to by checking cluster object lists
        sceneData.clusters.forEach((cluster, index) => {
          if (cluster.objects && cluster.objects.includes(obj.id)) {
            clusterId = index;
          } else if (cluster.object_ids && cluster.object_ids.includes(obj.id)) {
            clusterId = index;
          } else if (cluster.member_objects && cluster.member_objects.includes(obj.id)) {
            clusterId = index;
          }
        });
      }
      
      // Assign color based on cluster
      if (clusterId >= 0) {
        color = clusterColors[clusterId % clusterColors.length];
      }

      // Draw object circle (no labels)
      ctx.fillStyle = color;
      ctx.strokeStyle = "white";
      ctx.lineWidth = 2;

      ctx.beginPath();
      ctx.arc(pixelX, -pixelY, 8, 0, 2 * Math.PI); // Negative Y to match screen coordinates
      ctx.fill();
      ctx.stroke();
    }
  });
}

function drawClusters() {
  // Scale factor to convert meters to pixels for visualization
  const metersToPixels = 100;
  
  sceneData.clusters.forEach((cluster, index) => {
    if (
      cluster.cluster_center &&
      cluster.cluster_center.x !== undefined &&
      cluster.cluster_center.y !== undefined
    ) {
      // Convert meter coordinates to pixel coordinates
      const centerX = cluster.cluster_center.x * metersToPixels;
      const centerY = -cluster.cluster_center.y * metersToPixels; // Negative Y to match screen coordinates
      const color = clusterColors[index % clusterColors.length];

      // Draw cluster boundary/area
      if (cluster.bounding_box) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.setLineDash([5, 5]);

        const box = cluster.bounding_box;
        // Convert bounding box coordinates from meters to pixels
        const boxMinX = box.min_x * metersToPixels;
        const boxMaxX = box.max_x * metersToPixels;
        const boxMinY = box.min_y * metersToPixels;
        const boxMaxY = box.max_y * metersToPixels;
        
        ctx.beginPath();
        ctx.rect(
          boxMinX,
          -boxMaxY, // Flip Y coordinates
          boxMaxX - boxMinX,
          boxMaxY - boxMinY,
        );
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Draw cluster center (no labels)
      ctx.fillStyle = color;
      ctx.strokeStyle = "white";
      ctx.lineWidth = 3;

      ctx.beginPath();
      ctx.arc(centerX, centerY, 15, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
    }
  });
}

function getObjectCoordinates(obj) {
  // Try to extract coordinates from various possible fields
  if (obj.translation && obj.translation.length >= 2) {
    return { x: obj.translation[0], y: obj.translation[1] };
  }

  if (obj.x !== undefined && obj.y !== undefined) {
    return { x: obj.x, y: obj.y };
  }

  if (obj.center_x !== undefined && obj.center_y !== undefined) {
    return { x: obj.center_x, y: obj.center_y };
  }

  if (obj.cx !== undefined && obj.cy !== undefined) {
    return { x: obj.cx, y: obj.cy };
  }

  return null;
}

// Mouse interaction handlers
function onMouseDown(e) {
  isDragging = true;
  lastMousePos = getMousePos(e);
  canvas.style.cursor = "grabbing";
}

function onMouseMove(e) {
  const mousePos = getMousePos(e);

  // Update coordinate display
  const worldPos = screenToWorld(mousePos.x, mousePos.y);
  document.getElementById("coordinates").textContent =
    `X: ${worldPos.x.toFixed(3)}m, Y: ${worldPos.y.toFixed(3)}m`;

  if (isDragging) {
    const deltaX = mousePos.x - lastMousePos.x;
    const deltaY = mousePos.y - lastMousePos.y;

    viewOffset.x += deltaX / zoomLevel;
    viewOffset.y += deltaY / zoomLevel;

    draw();
  }

  lastMousePos = mousePos;
}

function onMouseUp(e) {
  isDragging = false;
  canvas.style.cursor = "crosshair";
}

function onMouseLeave(e) {
  isDragging = false;
  canvas.style.cursor = "crosshair";
}

function onWheel(e) {
  e.preventDefault();

  const mousePos = getMousePos(e);
  const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;

  // Zoom towards mouse position
  const worldPosBeforeZoom = screenToWorld(mousePos.x, mousePos.y);
  zoomLevel *= zoomFactor;
  zoomLevel = Math.max(0.1, Math.min(10, zoomLevel));

  const worldPosAfterZoom = screenToWorld(mousePos.x, mousePos.y);
  viewOffset.x += worldPosBeforeZoom.x - worldPosAfterZoom.x;
  viewOffset.y += worldPosBeforeZoom.y - worldPosAfterZoom.y;

  draw();
}

function getMousePos(e) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  };
}

function screenToWorld(screenX, screenY) {
  // Scale factor to convert between meters and pixels
  const metersToPixels = 100;
  
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;

  return {
    x: ((screenX - centerX) / zoomLevel - viewOffset.x) / metersToPixels,
    y: -(((screenY - centerY) / zoomLevel - viewOffset.y) / metersToPixels), // Flip Y coordinate and convert to meters
  };
}

// Zoom and view controls
function zoom(factor) {
  zoomLevel *= factor;
  zoomLevel = Math.max(0.1, Math.min(10, zoomLevel));
  draw();
}

function resetView() {
  viewOffset = { x: 0, y: 0 };
  zoomLevel = 0.8; // Better default zoom for meter-based coordinates
  hasAutoFittedScene = false; // Reset auto-fit flag to allow re-centering
  
  // Force auto-fit to center objects
  if (sceneData.objects || sceneData.clusters) {
    // Trigger a redraw which will auto-fit the view
    draw();
  } else {
    draw();
  }
}

// Animation loop
function animate() {
  // Could add animations here if needed
  requestAnimationFrame(animate);
}
