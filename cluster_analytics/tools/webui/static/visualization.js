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
let lastClusterUpdateTime = null; // Track when clusters were last updated
let hasAutoFittedScene = false; // Track if we've auto-fitted the current scene
let isResettingClusters = false; // Track if a cluster reset is in progress

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

// Cluster colors (expanded palette with more diverse colors)
const clusterColors = [
  "#e74c3c", // Red
  "#3498db", // Blue
  "#2ecc71", // Green
  "#f39c12", // Orange
  "#9b59b6", // Purple
  "#1abc9c", // Turquoise
  "#e67e22", // Dark Orange
  "#34495e", // Dark Blue Gray
  "#f1c40f", // Yellow
  "#e91e63", // Pink
  "#00bcd4", // Cyan
  "#4caf50", // Light Green
  "#ff9800", // Amber
  "#673ab7", // Deep Purple
  "#795548", // Brown
  "#607d8b", // Blue Gray
  "#ff5722", // Deep Orange
  "#009688", // Teal
  "#8bc34a", // Light Green
  "#ffc107", // Gold
  "#9c27b0", // Purple
  "#2196f3", // Light Blue
  "#ff6b6b", // Light Red
  "#4ecdc4", // Light Turquoise
  "#45b7d1", // Sky Blue
  "#6c5ce7", // Violet
  "#fd79a8", // Light Pink
  "#00b894", // Sea Green
  "#0984e3", // Ocean Blue
  "#fdcb6e", // Peach
  "#a29bfe", // Lavender
  "#fab1a0", // Salmon
  "#00cec9", // Robin Egg Blue
  "#6c5ce7", // Periwinkle
  "#fd79a8", // Hot Pink
];

// Map to store persistent color assignments for cluster UUIDs
const clusterColorMap = new Map();

// Function to generate consistent color from UUID string
function getClusterColor(uuid) {
  if (!uuid) return categoryColors.default;

  // Check if we already have a color for this UUID
  if (clusterColorMap.has(uuid)) {
    return clusterColorMap.get(uuid);
  }

  // Enhanced hash function for better distribution
  let hash = 0;
  for (let i = 0; i < uuid.length; i++) {
    const char = uuid.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32-bit integer
    hash = Math.abs(hash); // Ensure positive
  }

  // Use multiple hash variations to get better color distribution
  const hash1 = hash % clusterColors.length;
  const hash2 = Math.floor(hash / clusterColors.length) % clusterColors.length;
  const hash3 =
    Math.floor(hash / (clusterColors.length * clusterColors.length)) %
    clusterColors.length;

  // Try to find a color that's not already in use by other clusters
  const usedColors = new Set(clusterColorMap.values());

  // Priority order: try hash1, then hash2, then hash3, then any available
  const candidates = [hash1, hash2, hash3];

  for (const candidateIndex of candidates) {
    const candidateColor = clusterColors[candidateIndex];
    if (!usedColors.has(candidateColor)) {
      clusterColorMap.set(uuid, candidateColor);
      return candidateColor;
    }
  }

  // If all preferred candidates are taken, find the first unused color
  for (let i = 0; i < clusterColors.length; i++) {
    const color = clusterColors[i];
    if (!usedColors.has(color)) {
      clusterColorMap.set(uuid, color);
      return color;
    }
  }

  // If all colors are used (more clusters than colors), fall back to hash-based selection
  const color = clusterColors[hash1];
  clusterColorMap.set(uuid, color);
  return color;
}

// Function to create a color map for all current clusters
function createClusterColorMap() {
  const colorMap = new Map();

  if (sceneData.clusters && sceneData.clusters.length > 0) {
    sceneData.clusters.forEach((cluster) => {
      if (cluster.id) {
        // Get or generate color for this id
        colorMap.set(cluster.id, getClusterColor(cluster.id));
      }
    });
  }

  return colorMap;
}

// Utility function to convert hex color to rgba with transparency
function hexToRgba(hex, alpha = 0.3) {
  // Remove # if present
  hex = hex.replace("#", "");

  // Parse hex color
  const r = parseInt(hex.substr(0, 2), 16);
  const g = parseInt(hex.substr(2, 2), 16);
  const b = parseInt(hex.substr(4, 2), 16);

  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

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
  const refreshRateSelect = document.getElementById("refreshRateSelect");
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

  // Refresh rate selection
  refreshRateSelect.addEventListener("change", function () {
    const refreshRate = parseFloat(this.value);
    socket.emit("set_refresh_rate", { refresh_rate: refreshRate });

    // Update UI to show current setting
    const statusText = refreshRate === 0 ? "Real-time" : `${refreshRate}s`;
    console.log(`Refresh rate changed to: ${statusText}`);
  });

  // Movement vectors toggle
  const showMovementVectors = document.getElementById("showMovementVectors");
  showMovementVectors.addEventListener("change", function () {
    console.log(`Movement vectors: ${this.checked ? "enabled" : "disabled"}`);
    draw(); // Redraw the canvas with/without movement vectors
  });

  // Vector scale slider
  const vectorScale = document.getElementById("vectorScale");
  const vectorScaleValue = document.getElementById("vectorScaleValue");
  vectorScale.addEventListener("input", function () {
    vectorScaleValue.textContent = this.value;
    draw(); // Redraw the canvas with new vector scale
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

  socket.on("refresh_rate_updated", function (data) {
    const refreshRate = data.refresh_rate;
    const statusText = refreshRate === 0 ? "Real-time" : `${refreshRate}s`;
    console.log(`Refresh rate confirmed: ${statusText}`);
  });

  socket.on("clustering_config", function (data) {
    updateClusteringConfig(data);
  });

  socket.on("clustering_config_updated", function (data) {
    if (data.category) {
      console.log(
        `Clustering config updated for ${data.category}: eps=${data.eps}, min_samples=${data.min_samples}, is_default=${data.is_default}`,
      );

      // Update the specific category inputs in the UI
      const epsInput = document.getElementById(`eps-${data.category}`);
      const minSamplesInput = document.getElementById(
        `min-samples-${data.category}`,
      );

      if (epsInput && minSamplesInput) {
        epsInput.value = data.eps;
        minSamplesInput.value = data.min_samples;

        // Update the category display to reflect default/custom status
        const categoryElement = epsInput.closest(".clustering-category");
        if (categoryElement) {
          const statusSpan = categoryElement.querySelector("h4 span");
          if (statusSpan) {
            statusSpan.textContent = data.is_default ? "" : "(custom values)";
          }

          // Update reset button visibility based on server response
          const resetButton =
            categoryElement.querySelector(".clustering-reset");
          if (resetButton) {
            if (data.is_default) {
              resetButton.style.display = "none";
            } else {
              resetButton.style.display = "block";
            }
          }
        }
      }
    } else {
      console.error("Invalid clustering config update data:", data);
    }
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
  console.log(`Switching to scene: ${sceneId} (clearing all historic data)`);

  currentScene = sceneId;
  hasAutoFittedScene = false; // Reset auto-fit flag for new scene
  isResettingClusters = false; // Clear reset flag when switching scenes
  lastClusterUpdateTime = null; // Clear cluster timestamp for new scene
  socket.emit("select_scene", { scene_id: sceneId });

  // Explicitly clear ALL current data (objects and clusters) to prevent historic data display
  sceneData = { objects: [], clusters: [], metadata: {} };

  console.log("All historic cluster and object data cleared for new scene");
  updateUI();
  draw(); // Immediately redraw with cleared data
}

function updateSceneData(data) {
  if (data.scene_id === currentScene) {
    console.log(
      `Updating scene data for current scene ${data.scene_id}: ${data.data?.objects?.length || 0} objects, ${data.data?.clusters?.length || 0} clusters`,
    );

    // Replace all scene data with current data (no accumulation of historic data)
    sceneData = data.data || { objects: [], clusters: [], metadata: {} };

    console.log(
      `Scene data updated - now have ${sceneData.objects?.length || 0} objects and ${sceneData.clusters?.length || 0} clusters`,
    );

    updateUI();
    draw();
  } else {
    console.log(
      `Ignoring scene data update for scene ${data.scene_id} - current scene is ${currentScene}`,
    );
  }
}

function updateClusters(data) {
  if (data.scene_id === currentScene) {
    const now = Date.now();

    // Explicitly replace all clusters with current data (no accumulation)
    console.log(
      `Updating clusters for scene ${data.scene_id}: ${data.clusters?.length || 0} clusters (replacing any previous clusters)`,
    );
    console.log(
      `Previous cluster update: ${lastClusterUpdateTime ? new Date(lastClusterUpdateTime).toISOString() : "never"}, Current update: ${new Date(now).toISOString()}`,
    );

    sceneData.clusters = data.clusters || []; // Ensure we always have an array
    lastClusterUpdateTime = now; // Track when current clusters were received

    // DEBUG: Log cluster data structure to see if id exists
    console.log(
      "DEBUG: Cluster data structure:",
      JSON.stringify(data.clusters, null, 2),
    );
    if (data.clusters && data.clusters.length > 0) {
      console.log("DEBUG: First cluster structure:", data.clusters[0]);
      console.log("DEBUG: First cluster id:", data.clusters[0].id);
      console.log(
        "DEBUG: First cluster object_ids:",
        data.clusters[0].object_ids,
      );
    }
    lastClusterUpdateTime = now; // Track when this current data was received

    // Clear reset flag when new clusters arrive
    if (isResettingClusters) {
      isResettingClusters = false;
      console.log("Reset complete - new clusters received");
    }

    updateUI();
    draw();
  } else {
    console.log(
      `Ignoring cluster update for scene ${data.scene_id} - current scene is ${currentScene}`,
    );
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

  // Create simple legend items without colors
  Object.entries(categoryCounts).forEach(([category, count]) => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = `${category}: ${count}`;
    container.appendChild(item);
  });
}

function updateClusterLegend() {
  const container = document.getElementById("clusterLegend");
  container.innerHTML = "";

  // Debug: Log cluster data
  console.log(
    "DEBUG updateClusterLegend: sceneData.clusters =",
    sceneData.clusters,
  );

  // Show special message if reset is in progress
  if (
    isResettingClusters &&
    (!sceneData.clusters || sceneData.clusters.length === 0)
  ) {
    container.innerHTML =
      '<div class="no-data" style="color: #f39c12;">🔄 Recalculating clusters with default parameters...</div>';
    return;
  }

  if (!sceneData.clusters || sceneData.clusters.length === 0) {
    container.innerHTML = '<div class="no-data">No clusters found</div>';
    return;
  }

  sceneData.clusters.forEach((cluster, index) => {
    // Use id for consistent coloring, fallback to index-based for compatibility
    const color = cluster.id
      ? getClusterColor(cluster.id)
      : clusterColors[index % clusterColors.length];
    const movementType = cluster.velocity_analysis?.movement_type || "unknown";
    const shape = cluster.shape_analysis?.shape || "unknown";

    // Get velocity information
    const velocity = cluster.velocity_analysis?.average_velocity || [0, 0, 0];
    const speed = cluster.velocity_analysis?.velocity_magnitude || 0;
    const direction =
      cluster.velocity_analysis?.movement_direction_degrees || 0;

    // Format velocity information
    let velocityInfo = "";
    if (speed > 0.1) {
      const directionStr = Math.round(direction);
      velocityInfo = `<div style="margin-bottom: 4px;"><strong>Speed:</strong> ${speed.toFixed(1)} m/s @ ${directionStr}°</div>`;
    } else {
      velocityInfo = `<div style="margin-bottom: 4px;"><strong>Speed:</strong> stationary</div>`;
    }

    // Special handling for insufficient_points clusters
    // Use id for title if available, otherwise fallback to index
    let clusterTitle = cluster.id
      ? `Cluster ${cluster.id.substring(0, 8)}`
      : `Cluster ${index + 1}`;
    let shapeDisplay = shape;
    let additionalInfo = "";

    if (shape === "insufficient_points") {
      shapeDisplay = "irregular";
      additionalInfo = ``;
    }

    // Add id info if available
    let clusterIdInfo = "";
    if (cluster.id) {
      clusterIdInfo = `<div class="cluster-id-field" style="margin-bottom: 4px; font-family: monospace; font-size: 10px; color: #888; cursor: pointer; user-select: none;" 
                           title="Click to copy full UUID to clipboard">
                         <strong>ID:</strong> ${cluster.id}
                       </div>`;
    }

    // Get cluster state info if available
    let stateInfo = "";
    let stateColor = "#95a5a6"; // Default gray
    if (cluster.tracking && cluster.tracking.state) {
      const state = cluster.tracking.state;
      // Set state colors based on cluster state
      switch (state) {
        case "new":
          stateColor = "#f39c12"; // Orange
          break;
        case "active":
          stateColor = "#2ecc71"; // Green
          break;
        case "stable":
          stateColor = "#3498db"; // Blue
          break;
        case "fading":
          stateColor = "#e67e22"; // Dark Orange
          break;
        case "lost":
          stateColor = "#e74c3c"; // Red
          break;
        default:
          stateColor = "#95a5a6"; // Gray
      }

      stateInfo = `<div style="margin-bottom: 4px;"><strong>State:</strong> <span style="color: ${stateColor}; font-weight: bold;">${state}</span></div>`;
    }

    const clusterDiv = document.createElement("div");
    clusterDiv.className = "cluster-info";
    clusterDiv.innerHTML = `
            <div class="legend-item">
                <div class="legend-color" style="background-color: ${color}"></div>
                <strong>${clusterTitle}</strong>
            </div>
            <div style="margin-left: 24px; font-size: 12px; line-height: 1.4;">
                ${clusterIdInfo}
                ${stateInfo}
                <div style="margin-bottom: 4px;"><strong>Objects:</strong> ${cluster.objects_count || 0}</div>
                <div style="margin-bottom: 4px;"><strong>Category:</strong> ${cluster.category || "mixed"}</div>
                <div style="margin-bottom: 4px;"><strong>Shape:</strong> ${shapeDisplay}</div>
                ${additionalInfo}
                ${velocityInfo}
                <div style="color: #e67e22;"><strong>Movement:</strong> ${movementType}</div>
            </div>
        `;

    // Add click event listener for cluster ID copying
    if (cluster.id) {
      const idField = clusterDiv.querySelector(".cluster-id-field");
      if (idField) {
        idField.addEventListener("click", function () {
          copyToClipboard(cluster.id, this);
        });
      }
    }

    container.appendChild(clusterDiv);
  });
}

function updateClusteringConfig(data) {
  const container = document.getElementById("clusteringConfig");
  container.innerHTML = "";

  if (!data.categories || data.categories.length === 0) {
    container.innerHTML =
      '<div class="no-data">Select a scene to configure clustering</div>';
    return;
  }

  // Create configuration forms for each category
  data.categories.forEach((category) => {
    const config = data.config[category];
    if (!config) return;

    const categoryDiv = document.createElement("div");
    categoryDiv.className = "clustering-category";

    // Show status for custom values only
    const statusText = config.is_default ? "" : "(custom values)";
    const defaultInfo = `Default: eps=${config.default_eps}, min_samples=${config.default_min_samples}`;

    categoryDiv.innerHTML = `
      <h4>${escapeHTML(category)} <span style="color: #666; font-size: 0.8em;">${statusText}</span></h4>
      <div style="font-size: 0.8em; color: #888; margin-bottom: 8px;">${defaultInfo}</div>
      <div class="clustering-param">
        <label for="eps-${category}">Eps:</label>
        <input type="number" id="eps-${category}" value="${config.eps}" 
               min="0.1" max="20" step="0.1" 
               data-category="${category}" data-param="eps">
      </div>
      <div class="clustering-param">
        <label for="min-samples-${category}">Min Objects:</label>
        <input type="number" id="min-samples-${category}" value="${config.min_samples}" 
               min="1" max="20" step="1" 
               data-category="${category}" data-param="min_samples">
      </div>
      <div class="clustering-buttons" style="margin-top: 8px; display: flex; gap: 8px; flex-direction: column;">
        <button class="clustering-apply" onclick="applyClusteringConfig('${category}')">
          Apply for ${escapeHTML(category)}
        </button>
        <button class="clustering-reset" onclick="resetClusteringConfig('${category}')" style="display: ${config.is_default ? "none" : "block"};">
          Reset to Defaults
        </button>
      </div>
    `;

    container.appendChild(categoryDiv);
  });
}

function applyClusteringConfig(category) {
  const epsInput = document.getElementById(`eps-${category}`);
  const minSamplesInput = document.getElementById(`min-samples-${category}`);

  if (!epsInput || !minSamplesInput) {
    console.error(`Could not find inputs for category: ${category}`);
    return;
  }

  const eps = parseFloat(epsInput.value);
  const minSamples = parseInt(minSamplesInput.value);

  if (isNaN(eps) || isNaN(minSamples) || eps <= 0 || minSamples <= 0) {
    alert("Please enter valid positive numbers for clustering parameters");
    return;
  }

  // Send configuration update to server
  socket.emit("update_clustering_config", {
    category: category,
    eps: eps,
    min_samples: minSamples,
  });

  // Show the Reset button for this category after applying custom parameters
  const resetButton = document
    .querySelector(`#eps-${category}`)
    .closest(".clustering-category")
    .querySelector(".clustering-reset");
  if (resetButton) {
    resetButton.style.display = "block";
  }

  // Disable button temporarily to prevent rapid clicks
  const button = event.target;
  button.disabled = true;
  button.textContent = "Applying...";

  setTimeout(() => {
    button.disabled = false;
    button.textContent = `Apply for ${category}`;
  }, 2000);
}

function resetClusteringConfig(category) {
  // Set reset flag
  isResettingClusters = true;

  // Clear existing clusters immediately to avoid showing old results with new parameters
  if (sceneData.clusters) {
    console.log("Clearing existing clusters before reset");
    sceneData.clusters = [];
    updateUI();
    draw();
  }

  // Send reset request to server with current scene information
  socket.emit("reset_clustering_config", {
    category: category,
    scene_id: currentScene,
  });

  // Hide the Reset button after resetting to defaults
  const button = event.target;
  setTimeout(() => {
    button.style.display = "none";
  }, 2000);

  // Disable button temporarily to prevent rapid clicks
  button.disabled = true;
  button.textContent = "Resetting...";

  setTimeout(() => {
    button.disabled = false;
    button.textContent = "Reset to Defaults";
  }, 2000);
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
  if (
    !hasAutoFittedScene &&
    (sceneData.objects?.length > 0 || sceneData.clusters?.length > 0)
  ) {
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

  // Draw clusters (only current clusters, never historic data)
  if (sceneData.clusters && sceneData.clusters.length > 0) {
    console.log(
      `Drawing ${sceneData.clusters.length} current clusters for scene ${currentScene}`,
    );
    drawClusters();
  }

  // Restore context
  ctx.restore();
}

function autoFitView() {
  const metersToPixels = 100;
  let minX = Infinity,
    maxX = -Infinity;
  let minY = Infinity,
    maxY = -Infinity;
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
      if (
        cluster.center_of_mass &&
        cluster.center_of_mass.x !== undefined &&
        cluster.center_of_mass.y !== undefined
      ) {
        const centerX = cluster.center_of_mass.x * metersToPixels;
        const centerY = cluster.center_of_mass.y * metersToPixels;

        minX = Math.min(minX, centerX);
        maxX = Math.max(maxX, centerX);
        minY = Math.min(minY, centerY);
        maxY = Math.max(maxY, centerY);
        hasObjects = true;
      }
    });
  }

  // If we have objects, center the view
  if (
    hasObjects &&
    isFinite(minX) &&
    isFinite(maxX) &&
    isFinite(minY) &&
    isFinite(maxY)
  ) {
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

    if (
      Math.abs(currentCenterX - centerX) > centerThreshold ||
      Math.abs(currentCenterY - centerY) > centerThreshold ||
      Math.abs(zoomLevel - optimalZoom) > zoomThreshold
    ) {
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
  for (
    let x = Math.floor(gridStartX / gridSpacing) * gridSpacing;
    x <= gridEndX;
    x += gridSpacing
  ) {
    ctx.beginPath();
    ctx.moveTo(x, gridStartY);
    ctx.lineTo(x, gridEndY);
    ctx.stroke();
  }

  // Horizontal minor grid lines
  for (
    let y = Math.floor(gridStartY / gridSpacing) * gridSpacing;
    y <= gridEndY;
    y += gridSpacing
  ) {
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
  for (
    let x = Math.floor(gridStartX / majorGridSpacing) * majorGridSpacing;
    x <= gridEndX;
    x += majorGridSpacing
  ) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.2)"; // Match the increased opacity
    ctx.beginPath();
    ctx.moveTo(x, gridStartY);
    ctx.lineTo(x, gridEndY);
    ctx.stroke();

    // Add labels for positive values and zero (but limit labels to visible area)
    const meterValue = x / metersToPixels;
    if (meterValue >= 0 && meterValue % 1 === 0 && meterValue <= 50) {
      // Only show labels up to 50m for clarity
      ctx.fillText(`${meterValue.toFixed(0)}m`, x, gridStartY + 15);
    }
  }

  // Horizontal major grid lines with labels
  for (
    let y = Math.floor(gridStartY / majorGridSpacing) * majorGridSpacing;
    y <= gridEndY;
    y += majorGridSpacing
  ) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.2)"; // Match the increased opacity
    ctx.beginPath();
    ctx.moveTo(gridStartX, y);
    ctx.lineTo(gridEndX, y);
    ctx.stroke();

    // Add labels for positive values and zero (but limit labels to visible area)
    const meterValue = -y / metersToPixels; // Negative because Y is flipped
    if (meterValue >= 0 && meterValue % 1 === 0 && meterValue <= 50) {
      // Only show labels up to 50m for clarity
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

  console.log(
    `Drawing ${sceneData.objects?.length || 0} objects for scene ${currentScene}`,
  );

  if (!sceneData.objects || sceneData.objects.length === 0) {
    console.log("No objects to draw");
    return;
  }

  // Debug: Log objects data
  console.log(
    "DEBUG drawObjects: sceneData.objects[0] =",
    sceneData.objects[0],
  );
  console.log("DEBUG drawObjects: sceneData.clusters =", sceneData.clusters);

  // Create color mapping for cluster IDs
  const colorMap = createClusterColorMap();
  console.log("DEBUG drawObjects: colorMap =", colorMap);

  sceneData.objects.forEach((obj) => {
    const coords = getObjectCoordinates(obj);
    if (coords) {
      // Convert meter coordinates to pixel coordinates
      const pixelX = coords.x * metersToPixels;
      const pixelY = coords.y * metersToPixels;

      // Determine object color based on cluster assignment
      let color = categoryColors.default; // Default gray for unclustered objects
      let clusterUuid = null;

      // Find which cluster this object belongs to by checking cluster object lists
      if (sceneData.clusters) {
        sceneData.clusters.forEach((cluster) => {
          if (cluster.object_ids && cluster.object_ids.includes(obj.id)) {
            clusterUuid = cluster.id;
          } else if (cluster.objects && cluster.objects.includes(obj.id)) {
            clusterUuid = cluster.id;
          } else if (
            cluster.member_objects &&
            cluster.member_objects.includes(obj.id)
          ) {
            clusterUuid = cluster.id;
          }
        });
      }

      // Debug: Log cluster assignment for first few objects
      if (sceneData.objects.indexOf(obj) < 3) {
        console.log(
          `DEBUG drawObjects: obj.id=${obj.id}, clusterUuid=${clusterUuid}`,
        );
      }

      // Assign color based on id
      if (clusterUuid) {
        color = colorMap.get(clusterUuid) || getClusterColor(clusterUuid);
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

  // Create color mapping for cluster IDs
  const colorMap = createClusterColorMap();

  sceneData.clusters.forEach((cluster, index) => {
    if (
      cluster.center_of_mass &&
      cluster.center_of_mass.x !== undefined &&
      cluster.center_of_mass.y !== undefined
    ) {
      // Use id for consistent coloring, fallback to index-based for compatibility
      const color = cluster.id
        ? colorMap.get(cluster.id) || getClusterColor(cluster.id)
        : clusterColors[index % clusterColors.length];
      const centerX = cluster.center_of_mass.x * metersToPixels;
      const centerY = -cluster.center_of_mass.y * metersToPixels; // Negative Y to match screen coordinates
      const shapeType = cluster.shape_analysis?.shape; // Declare once at the top

      // Set transparent fill and stroked border
      const transparentColor = hexToRgba(color, 0.3); // 30% opacity
      ctx.fillStyle = transparentColor;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.setLineDash([]);

      // Draw shape based on shape analysis data
      const shapeData = cluster.shape_analysis;
      if (shapeData && shapeData.shape) {
        switch (shapeData.shape) {
          case "circle":
            if (shapeData.size && shapeData.size.radius) {
              const radius = shapeData.size.radius * metersToPixels;
              ctx.beginPath();
              ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
              ctx.fill();
              ctx.stroke();
            }
            break;

          case "rectangle":
            if (shapeData.size && shapeData.size.corner_points) {
              ctx.beginPath();
              const corners = shapeData.size.corner_points;
              if (corners.length >= 4) {
                // Move to first corner
                ctx.moveTo(
                  corners[0][0] * metersToPixels,
                  -corners[0][1] * metersToPixels,
                );
                // Draw lines to other corners
                for (let i = 1; i < corners.length; i++) {
                  ctx.lineTo(
                    corners[i][0] * metersToPixels,
                    -corners[i][1] * metersToPixels,
                  );
                }
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
              }
            } else if (
              shapeData.size &&
              shapeData.size.width &&
              shapeData.size.height
            ) {
              // Fallback: draw rectangle around center
              const width = shapeData.size.width * metersToPixels;
              const height = shapeData.size.height * metersToPixels;
              ctx.beginPath();
              ctx.rect(
                centerX - width / 2,
                centerY - height / 2,
                width,
                height,
              );
              ctx.fill();
              ctx.stroke();
            }
            break;

          case "line":
            if (shapeData.size && shapeData.size.endpoints) {
              const endpoints = shapeData.size.endpoints;
              if (endpoints.length >= 2) {
                // Draw line with some width for visibility
                const lineWidth = Math.max(
                  10,
                  (shapeData.size.width_spread || 0.5) * metersToPixels,
                );
                ctx.lineWidth = lineWidth;
                ctx.lineCap = "round";

                ctx.beginPath();
                ctx.moveTo(
                  endpoints[0][0] * metersToPixels,
                  -endpoints[0][1] * metersToPixels,
                );
                ctx.lineTo(
                  endpoints[1][0] * metersToPixels,
                  -endpoints[1][1] * metersToPixels,
                );
                ctx.stroke();

                // Reset line width
                ctx.lineWidth = 2;
                ctx.lineCap = "butt";
              }
            }
            break;

          case "insufficient_points":
            // For clusters with insufficient points, don't draw cluster shape
            // Objects will be colored individually in drawObjects function
            console.log(
              `Cluster ${index + 1}: insufficient_points - objects will be colored individually`,
            );
            break;

          case "irregular":
          default:
            // For irregular shapes, use bounding box or fall back to circle
            if (
              shapeData.size &&
              shapeData.size.bounding_width &&
              shapeData.size.bounding_height
            ) {
              const width = shapeData.size.bounding_width * metersToPixels;
              const height = shapeData.size.bounding_height * metersToPixels;
              ctx.beginPath();
              ctx.rect(
                centerX - width / 2,
                centerY - height / 2,
                width,
                height,
              );
              ctx.fill();
              ctx.stroke();
            } else {
              // Ultimate fallback: simple circle
              ctx.beginPath();
              ctx.arc(centerX, centerY, 50, 0, 2 * Math.PI); // 50px default radius
              ctx.fill();
              ctx.stroke();
            }
            break;
        }
      } else {
        // No shape data available, fall back to bounding box if available
        if (cluster.bounding_box) {
          const box = cluster.bounding_box;
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
          ctx.fill();
          ctx.stroke();
        } else {
          // Ultimate fallback: simple circle
          ctx.beginPath();
          ctx.arc(centerX, centerY, 50, 0, 2 * Math.PI);
          ctx.fill();
          ctx.stroke();
        }
      }

      // Draw movement vector if velocity data is available, user has enabled it, and it's not an insufficient_points cluster
      const showVectors = document.getElementById(
        "showMovementVectors",
      ).checked;
      if (
        showVectors &&
        shapeType !== "insufficient_points" &&
        cluster.velocity_analysis &&
        cluster.velocity_analysis.average_velocity
      ) {
        const velocity = cluster.velocity_analysis.average_velocity;
        const speed = cluster.velocity_analysis.velocity_magnitude || 0;

        // Only draw vector if there's significant movement (speed > 0.1 m/s)
        if (speed > 0.1) {
          // Calculate vector end point (scale velocity for visualization)
          const vectorScale = document.getElementById("vectorScale").value;
          const velocityScale = vectorScale; // Use slider value directly
          const vectorEndX = centerX + velocity[0] * velocityScale;
          const vectorEndY = centerY - velocity[1] * velocityScale; // Negative Y for screen coordinates

          // Draw movement vector arrow
          ctx.strokeStyle = color;
          ctx.fillStyle = color;
          ctx.lineWidth = 3;
          ctx.setLineDash([]);

          // Draw main vector line
          ctx.beginPath();
          ctx.moveTo(centerX, centerY);
          ctx.lineTo(vectorEndX, vectorEndY);
          ctx.stroke();

          // Draw arrowhead
          const arrowLength = 12;
          const arrowAngle = Math.PI / 6; // 30 degrees
          const vectorAngle = Math.atan2(
            vectorEndY - centerY,
            vectorEndX - centerX,
          );

          ctx.beginPath();
          ctx.moveTo(vectorEndX, vectorEndY);
          ctx.lineTo(
            vectorEndX - arrowLength * Math.cos(vectorAngle - arrowAngle),
            vectorEndY - arrowLength * Math.sin(vectorAngle - arrowAngle),
          );
          ctx.lineTo(
            vectorEndX - arrowLength * Math.cos(vectorAngle + arrowAngle),
            vectorEndY - arrowLength * Math.sin(vectorAngle + arrowAngle),
          );
          ctx.closePath();
          ctx.fill();

          // Add speed label near the arrow tip
          ctx.fillStyle = color;
          ctx.font = "12px Arial";
          ctx.textAlign = "center";
          ctx.fillText(
            `${speed.toFixed(1)} m/s`,
            vectorEndX + 15 * Math.cos(vectorAngle),
            vectorEndY + 15 * Math.sin(vectorAngle) + 4,
          );
        }
      }
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

// Function to copy text to clipboard
function copyToClipboard(text, element) {
  navigator.clipboard
    .writeText(text)
    .then(() => {
      // Visual feedback - temporarily change style
      const originalColor = element.style.color;
      const originalText = element.innerHTML;

      element.style.color = "#27ae60";
      element.innerHTML = "<strong>ID:</strong> Copied!";

      setTimeout(() => {
        element.style.color = originalColor;
        element.innerHTML = originalText;
      }, 1000);
    })
    .catch((err) => {
      console.error("Failed to copy text: ", err);
      // Fallback for older browsers
      const textArea = document.createElement("textarea");
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand("copy");
        // Visual feedback for fallback
        const originalColor = element.style.color;
        const originalText = element.innerHTML;

        element.style.color = "#27ae60";
        element.innerHTML = "<strong>ID:</strong> Copied!";

        setTimeout(() => {
          element.style.color = originalColor;
          element.innerHTML = originalText;
        }, 1000);
      } catch (err) {
        console.error("Fallback copy failed: ", err);
      }
      document.body.removeChild(textArea);
    });
}

// Animation loop
function animate() {
  // Could add animations here if needed
  requestAnimationFrame(animate);
}
