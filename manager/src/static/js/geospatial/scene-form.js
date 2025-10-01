"use strict";

// Scene form functionality
async function toggleMapFields() {
  var type = document.getElementById("mapType").value;
  console.log("Toggling map fields to:", type);

  document.getElementById("uploadFields").style.display =
    type === "upload" ? "" : "none";
  document.getElementById("geospatialFields").style.display =
    type === "geospatial" ? "" : "none";

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
      } catch (error) {
        console.error("Error initializing map:", error);
      }
    }, 100);
  }
}

// Setup event listeners when the DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  // Set up the initial state
  toggleMapFields();

  // Add event listener for map type changes
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
    button.addEventListener("click", function () {
      if (window.mapManager && typeof mapManager[action] === "function") {
        mapManager[action]();
      }
    });
  });

  // Add event listener for restore controls button (dynamically created)
  document.addEventListener("click", function (e) {
    if (e.target.textContent === "Restore Controls") {
      if (window.mapManager) {
        mapManager.restoreControls();
      }
    }
  });
});
