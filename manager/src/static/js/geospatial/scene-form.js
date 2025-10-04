"use strict";

// Get map type from dropdown (JavaScript only, not saved to database)
function getMapType() {
  const mapTypeField = document.getElementById("mapType");
  if (mapTypeField) {
    return mapTypeField.value;
  }
  return "upload"; // default
}

// Scene form functionality
async function toggleMapFields() {
  var type = getMapType();
  console.log("Toggling map fields to:", type);

  // Toggle upload fields
  document.getElementById("uploadFields").style.display =
    type === "upload" ? "" : "none";

  // Toggle geospatial fields - support both create and update page structures
  const geospatialFields = document.getElementById("geospatialFields");
  if (geospatialFields) {
    // Create page structure - single container
    geospatialFields.style.display = type === "geospatial" ? "" : "none";
    console.log(
      "Geospatial fields visibility:",
      geospatialFields.style.display,
    );
  } else {
    // Update page structure - individual elements
    const mapProviderRow = document.getElementById("mapProviderRow");
    const locationInputRow = document.getElementById("locationInputRow");
    const generateButtonRow = document.getElementById("generateButtonRow");
    const mapViewRow = document.getElementById("mapViewRow");

    if (mapProviderRow) {
      mapProviderRow.style.display = type === "geospatial" ? "" : "none";
    }
    if (locationInputRow) {
      locationInputRow.style.display = type === "geospatial" ? "" : "none";
    }
    if (generateButtonRow) {
      generateButtonRow.style.display = type === "geospatial" ? "" : "none";
    }
    if (mapViewRow) {
      mapViewRow.style.display = type === "geospatial" ? "" : "none";
    }
    console.log("Individual geospatial elements toggled for type:", type);
  }

  // Initialize map when geospatial fields become visible
  if (type === "geospatial") {
    console.log(
      "Geospatial selected, mapManager available:",
      !!window.mapManager,
    );

    // Ensure mapManager exists, if not create it
    if (!window.mapManager) {
      console.log("Creating new mapManager instance");
      window.mapManager = new GeoManager();
    }

    // Small delay to ensure the div is visible before initializing map
    setTimeout(async () => {
      try {
        console.log("Initializing map...");
        await window.mapManager.initialize();
        console.log("Map initialized successfully");
        // Ensure map container is visible when successful
        const mapContainer = document.getElementById("map");
        if (mapContainer) {
          mapContainer.style.display = "";
        }
      } catch (error) {
        console.error("Error initializing map:", error);
        // Hide the map container when initialization fails
        const mapContainer = document.getElementById("map");
        if (mapContainer) {
          mapContainer.style.display = "none";
        }
      }
    }, 100);
  }
}

// Setup event listeners when the DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  // Set up the initial state
  toggleMapFields();

  // Add event listener for map type dropdown (JavaScript only)
  const mapTypeSelect = document.getElementById("mapType");
  if (mapTypeSelect) {
    mapTypeSelect.addEventListener("change", toggleMapFields);
  }

  // Add event listener for map provider changes
  const mapProviderSelect = document.getElementById("mapProvider");
  if (mapProviderSelect) {
    mapProviderSelect.addEventListener("change", function () {
      if (window.switchMapProvider && typeof switchMapProvider === "function") {
        switchMapProvider();
      }
    });
  }

  // Add event listeners for geospatial buttons using data attributes
  const actionButtons = document.querySelectorAll("button[data-action]");
  actionButtons.forEach((button) => {
    const action = button.getAttribute("data-action");
    // Skip prepareScreenshot action
    if (action === "prepareScreenshot") {
      return;
    }
    button.addEventListener("click", function () {
      if (window.mapManager && typeof mapManager[action] === "function") {
        mapManager[action]();
      }
    });
  });
});
