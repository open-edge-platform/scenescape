// WebSocket connection for real-time updates
const socket = io();

// Canvas and visualization variables
let canvas, ctx;
let viewOffset = { x: 0, y: 0 };
let zoomLevel = 1;
let isDragging = false;
let lastMousePos = { x: 0, y: 0 };

// Data storage
let currentScene = null;
let sceneData = {
  objects: [],
  clusters: [],
  metadata: {},
};

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

  // Save context for transformations
  ctx.save();

  // Apply zoom and pan transformations
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.scale(zoomLevel, zoomLevel);
  ctx.translate(viewOffset.x, viewOffset.y);

  // Draw coordinate axes
  drawAxes();

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

function drawAxes() {
  const axisLength = 1000;

  ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
  ctx.lineWidth = 1;

  // X axis
  ctx.beginPath();
  ctx.moveTo(-axisLength, 0);
  ctx.lineTo(axisLength, 0);
  ctx.stroke();

  // Y axis
  ctx.beginPath();
  ctx.moveTo(0, -axisLength);
  ctx.lineTo(0, axisLength);
  ctx.stroke();

  // Grid lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
  for (let i = -axisLength; i <= axisLength; i += 50) {
    if (i !== 0) {
      // Vertical lines
      ctx.beginPath();
      ctx.moveTo(i, -axisLength);
      ctx.lineTo(i, axisLength);
      ctx.stroke();

      // Horizontal lines
      ctx.beginPath();
      ctx.moveTo(-axisLength, i);
      ctx.lineTo(axisLength, i);
      ctx.stroke();
    }
  }
}

function drawObjects() {
  sceneData.objects.forEach((obj) => {
    const coords = getObjectCoordinates(obj);
    if (coords) {
      const color = categoryColors[obj.category] || categoryColors.default;

      // Draw object circle
      ctx.fillStyle = color;
      ctx.strokeStyle = "white";
      ctx.lineWidth = 2;

      ctx.beginPath();
      ctx.arc(coords.x, -coords.y, 8, 0, 2 * Math.PI); // Negative Y to match screen coordinates
      ctx.fill();
      ctx.stroke();

      // Draw category label
      ctx.fillStyle = "white";
      const labelFontSize = getResponsiveFontSize(12);
      ctx.font = `${labelFontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(obj.category || "?", coords.x, -coords.y - 15);
    }
  });
}

function drawClusters() {
  sceneData.clusters.forEach((cluster, index) => {
    if (cluster.cluster_center && cluster.cluster_center.x !== undefined && cluster.cluster_center.y !== undefined) {
      const centerX = cluster.cluster_center.x;
      const centerY = -cluster.cluster_center.y; // Negative Y to match screen coordinates
      const color = clusterColors[index % clusterColors.length];

      // Draw cluster boundary/area
      if (cluster.bounding_box) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.setLineDash([5, 5]);

        const box = cluster.bounding_box;
        ctx.beginPath();
        ctx.rect(
          box.min_x,
          -box.max_y, // Flip Y coordinates
          box.max_x - box.min_x,
          box.max_y - box.min_y,
        );
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Draw cluster center
      ctx.fillStyle = color;
      ctx.strokeStyle = "white";
      ctx.lineWidth = 3;

      ctx.beginPath();
      ctx.arc(centerX, centerY, 15, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();

      // Draw cluster label
      ctx.fillStyle = "white";
      const clusterLabelFontSize = getResponsiveFontSize(14);
      const clusterInfoFontSize = getResponsiveFontSize(10);
      ctx.font = `bold ${clusterLabelFontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(`C${index + 1}`, centerX, centerY + 5);

      // Draw cluster info
      ctx.font = `${clusterInfoFontSize}px -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`;
      ctx.fillText(
        `${cluster.objects_in_cluster || 0} ${cluster.category || "objects"}`,
        centerX,
        centerY + 25,
      );
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
    `X: ${worldPos.x.toFixed(1)}, Y: ${worldPos.y.toFixed(1)}`;

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
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;

  return {
    x: (screenX - centerX) / zoomLevel - viewOffset.x,
    y: -((screenY - centerY) / zoomLevel - viewOffset.y), // Flip Y coordinate
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
  zoomLevel = 1;
  draw();
}

// Animation loop
function animate() {
  // Could add animations here if needed
  requestAnimationFrame(animate);
}
