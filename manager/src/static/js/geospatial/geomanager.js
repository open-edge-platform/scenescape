// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Application Main - Map Manager using Strategy Pattern
class GeoManager {
  constructor() {
    this.mapStrategy = null;
    this.currentProvider = "google";
  }

  async initialize() {
    await this.setMapProvider(this.currentProvider);
  }

  async setMapProvider(provider) {
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
      // Initialize the map with default configuration
      await this.mapStrategy.initialize("map", {
        lat: 37.7749,
        lng: -122.4194,
        zoom: 15,
        // Add NASA Earthdata token if needed (optional)
        // earthdataToken: "your-nasa-earthdata-token-here"
      });

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
    await mapManager.setMapProvider(provider);
    console.log(`Switched to ${provider} maps`);
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
