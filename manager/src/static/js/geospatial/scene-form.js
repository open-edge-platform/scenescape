// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Get map type from Django form field
function getMapType() {
  const mapTypeField = document.getElementById("id_map_type");
  if (mapTypeField) {
    const value = mapTypeField.value;
    // Convert Django field values to JavaScript values
    if (value === "geospatial_map") {
      return "geospatial";
    }
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

        // Load saved provider preference and update UI FIRST
        loadSavedMapProvider();

        // Load saved geospatial settings
        const savedSettings = loadSavedGeospatialSettings();

        await window.mapManager.initialize(savedSettings);
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

// Load saved geospatial settings from hidden form fields
window.loadSavedGeospatialSettings = function loadSavedGeospatialSettings() {
  const latField = document.getElementById("id_map_center_lat");
  const lngField = document.getElementById("id_map_center_lng");
  const zoomField = document.getElementById("id_map_zoom");
  const rotationField = document.getElementById("id_map_bearing");

  const settings = {};

  if (latField && latField.value) {
    settings.lat = parseFloat(latField.value);
  }
  if (lngField && lngField.value) {
    settings.lng = parseFloat(lngField.value);
  }
  if (zoomField && zoomField.value) {
    settings.zoom = parseFloat(zoomField.value);
  }
  if (rotationField && rotationField.value) {
    settings.rotation = parseFloat(rotationField.value);
  }

  console.log("Loaded saved geospatial settings:", settings);
  return settings;
};

// Load saved map provider and update UI
function loadSavedMapProvider() {
  const providerField = document.getElementById("id_geospatial_provider");
  const mapProviderSelect = document.getElementById("mapProvider");

  let selectedProvider = "google"; // default

  if (providerField && providerField.value) {
    selectedProvider = providerField.value;
    console.log("Found saved map provider:", selectedProvider);
  } else {
    console.log("No saved provider, using default:", selectedProvider);
    // Save the default to the form field
    if (providerField) {
      providerField.value = selectedProvider;
    }
  }

  // Update UI dropdown to match the provider
  if (mapProviderSelect) {
    mapProviderSelect.value = selectedProvider;
  }

  // Update GeoManager's current provider BEFORE initialization
  if (window.mapManager) {
    window.mapManager.currentProvider = selectedProvider;
    console.log("Set GeoManager provider to:", selectedProvider);
  }
}

// Generic function to save current map settings from any map instance
window.saveCurrentMapSettings = function saveCurrentMapSettings() {
  if (!window.mapManager || !window.mapManager.getCurrentMapInstance()) {
    return;
  }

  const map = window.mapManager.getCurrentMapInstance();
  const center = map.getCenter();
  const zoom = map.getZoom();

  // Use heading for both Google Maps (getHeading) and Mapbox (getBearing)
  const heading = (map.getHeading ? map.getHeading() : map.getBearing()) || 0;

  // Get provider from UI dropdown
  const provider = document.getElementById("mapProvider")?.value || "google";

  // Update hidden form fields
  const latField = document.getElementById("id_map_center_lat");
  const lngField = document.getElementById("id_map_center_lng");
  const zoomField = document.getElementById("id_map_zoom");
  const providerField = document.getElementById("id_geospatial_provider");
  const rotationField = document.getElementById("id_map_bearing");

  // Handle different coordinate access patterns (Google vs Mapbox)
  const lat = center.lat ? center.lat() : center.lat;
  const lng = center.lng ? center.lng() : center.lng;

  if (latField) latField.value = lat;
  if (lngField) lngField.value = lng;
  if (zoomField) zoomField.value = zoom;
  if (providerField) providerField.value = provider;
  if (rotationField) rotationField.value = heading;

  console.log("Saved map settings:", {
    lat: lat,
    lng: lng,
    zoom: zoom,
    provider: provider,
    rotation: heading,
  });
};

// Save current geospatial settings to hidden form fields
window.saveCurrentGeospatialSettings =
  function saveCurrentGeospatialSettings() {
    if (!window.mapManager || !window.mapManager.getCurrentMapInstance()) {
      return;
    }

    const center = window.mapManager.getCurrentMapInstance().getCenter();
    const zoom = window.mapManager.getCurrentMapInstance().getZoom();
    const provider = document.getElementById("mapProvider")?.value || "google";

    // Get rotation/bearing if available
    let rotation = 0;
    if (window.mapManager.getCurrentMapInstance().getBearing) {
      rotation = window.mapManager.getCurrentMapInstance().getBearing();
    }

    // Update hidden form fields
    const latField = document.getElementById("id_map_center_lat");
    const lngField = document.getElementById("id_map_center_lng");
    const zoomField = document.getElementById("id_map_zoom");
    const providerField = document.getElementById("id_geospatial_provider");
    const rotationField = document.getElementById("id_map_bearing");

    if (latField) {
      latField.value = center.lat || center.latitude || center[1];
    }
    if (lngField) {
      lngField.value = center.lng || center.longitude || center[0];
    }
    if (zoomField) {
      zoomField.value = zoom;
    }
    if (providerField) {
      providerField.value = provider;
    }
    if (rotationField) {
      rotationField.value = rotation;
    }

    console.log("Saved current geospatial settings:", {
      lat: latField?.value,
      lng: lngField?.value,
      zoom: zoomField?.value,
      provider: providerField?.value,
      rotation: rotationField?.value,
    });
  };

// Setup event listeners when the DOM is loaded
document.addEventListener("DOMContentLoaded", function () {
  // Load saved provider preference first (even before toggleMapFields)
  loadSavedMapProvider();

  // Set up the initial state
  toggleMapFields();

  // Add event listener for Django map type field
  const mapTypeSelect = document.getElementById("id_map_type");
  if (mapTypeSelect) {
    mapTypeSelect.addEventListener("change", toggleMapFields);
  }

  // Add event listener for map provider changes
  const mapProviderSelect = document.getElementById("mapProvider");
  if (mapProviderSelect) {
    mapProviderSelect.addEventListener("change", function () {
      // Immediately save the provider selection to the hidden form field
      const providerField = document.getElementById("id_geospatial_provider");
      if (providerField) {
        providerField.value = mapProviderSelect.value;
        console.log(
          "Provider changed, saved to form:",
          mapProviderSelect.value,
        );
      }

      // Also save any existing map settings before switching
      if (
        getMapType() === "geospatial" &&
        window.mapManager &&
        window.mapManager.getCurrentMapInstance()
      ) {
        saveCurrentGeospatialSettings();
        console.log("Saved current settings before provider switch");
      }

      // Then switch the map provider
      if (
        window.switchMapProvider &&
        typeof window.switchMapProvider === "function"
      ) {
        window.switchMapProvider();
      }
    });
  }

  // Add event listeners for geospatial buttons using data attributes
  const actionButtons = document.querySelectorAll("button[data-action]");
  actionButtons.forEach((button) => {
    const action = button.getAttribute("data-action");
    button.addEventListener("click", function () {
      if (window.mapManager && typeof mapManager[action] === "function") {
        // Save current settings before generating bounds/snapshot
        if (action === "generateBounds") {
          saveCurrentGeospatialSettings();
        }
        mapManager[action]();
      }
    });
  });

  // Add event listener to save geospatial settings before form submission
  const form = document.querySelector("form");
  if (form) {
    form.addEventListener("submit", function () {
      if (getMapType() === "geospatial") {
        saveCurrentGeospatialSettings();

        // Debug: Log all geospatial form values being submitted
        const providerField = document.getElementById("id_geospatial_provider");
        const latField = document.getElementById("id_map_center_lat");
        const lngField = document.getElementById("id_map_center_lng");
        const zoomField = document.getElementById("id_map_zoom");
        const bearingField = document.getElementById("id_map_bearing");

        console.log("Form submission - geospatial values:", {
          provider: providerField?.value,
          lat: latField?.value,
          lng: lngField?.value,
          zoom: zoomField?.value,
          bearing: bearingField?.value,
        });
      }
    });
  }
});
