// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Application Main - Map Manager using Strategy Pattern
class GeoManager {
  constructor() {
    this.mapStrategy = null;
    this.currentProvider = "google";
  }

  async initialize(config = {}) {
    await this.setMapProvider(this.currentProvider, config);
  }

  async setMapProvider(provider, config = {}) {
    // Clear existing map and reset container visibility
    const mapContainer = document.getElementById("map");
    if (this.mapStrategy && mapContainer) {
      mapContainer.innerHTML = "";
      mapContainer.style.display = ""; // Reset visibility for new provider
    }

    this.currentProvider = provider;

    // Initialize the appropriate strategy
    switch (provider) {
      case "google":
        this.mapStrategy = new GoogleMapsPlugin();
        break;
      case "mapbox":
        this.mapStrategy = new MapboxPlugin();
        break;
      default:
        throw new Error(`Unknown map provider: ${provider}`);
    }

    try {
      // Merge saved config with defaults
      const defaultConfig = {
        lat: 37.7749,
        lng: -122.4194,
        zoom: 15,
        rotation: 0,
      };

      const finalConfig = { ...defaultConfig, ...config };
      console.log("Initializing map with config:", finalConfig);

      // Initialize the map with configuration
      await this.mapStrategy.initialize("map", finalConfig);

      // Ensure map container is visible on successful initialization
      if (mapContainer) {
        mapContainer.style.display = "";
      }
    } catch (error) {
      // Hide map container on initialization failure
      if (mapContainer) {
        mapContainer.style.display = "none";
      }
      throw error; // Re-throw to maintain error handling chain
    }
  }

  moveToLocation() {
    const input = document.getElementById("locationInput").value;
    if (this.mapStrategy) {
      this.mapStrategy.moveToLocation(input);
    }
  }

  generateBounds() {
    if (this.mapStrategy) {
      this.mapStrategy.generateBounds();
    }
  }

  getCurrentProvider() {
    return this.currentProvider;
  }

  getMapStrategy() {
    return this.mapStrategy;
  }

  getCurrentMapInstance() {
    return this.mapStrategy ? this.mapStrategy.map : null;
  }
}

// Make GeoManager globally accessible
window.GeoManager = GeoManager;

// Global map manager instance
let mapManager;

// Initialize the application
window.addEventListener("load", async () => {
  mapManager = new GeoManager();
  window.mapManager = mapManager; // Make it globally accessible

  // Only initialize if geospatial fields are visible
  const geospatialFields = document.getElementById("geospatialFields");
  if (geospatialFields && geospatialFields.style.display !== "none") {
    await mapManager.initialize();
  }
});

// Switch map provider function
async function switchMapProvider() {
  const provider = document.getElementById("mapProvider").value;
  try {
    // Save the provider selection to the hidden form field immediately
    const providerField = document.getElementById("id_geospatial_provider");
    if (providerField) {
      providerField.value = provider;
      console.log("Saved provider to form field:", provider);
    }

    // Load current saved settings when switching providers
    const savedSettings = window.loadSavedGeospatialSettings
      ? window.loadSavedGeospatialSettings()
      : {};
    await mapManager.setMapProvider(provider, savedSettings);
    console.log(`Switched to ${provider} maps with settings:`, savedSettings);
  } catch (error) {
    console.error("Error switching map provider:", error);
  }
}

// Allow Enter key to trigger location search
document.addEventListener("DOMContentLoaded", () => {
  const locationInput = document.getElementById("locationInput");
  if (locationInput) {
    locationInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        mapManager.moveToLocation();
      }
    });
  }
});
