// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Mapbox Plugin Implementation
class MapboxPlugin extends MapInterface {
  constructor() {
    super();
    this.map = null;
    this.accessToken = this.getMapboxApiKey();
    // Note: Don't show modal in constructor - wait for initialize()
  }

  getMapboxApiKey() {
    // Then try to get from JSON script block (CSP-compliant)
    const scriptElement = document.getElementById("mapbox-api-key");
    if (scriptElement) {
      try {
        return JSON.parse(scriptElement.textContent);
      } catch (e) {
        console.error("Error parsing Mapbox API key from JSON script:", e);
      }
    }

    return "";
  }

  async initialize(containerId, config = {}) {
    // Check if access token is still empty and try to get it again
    if (!this.accessToken) {
      this.accessToken = this.getMapboxApiKey();
    }

    if (!this.accessToken) {
      this.showApiKeyModal({
        providerName: "Mapbox",
        envVarName: "MAPBOX_API_KEY",
        signupUrl: "https://account.mapbox.com/auth/signup/",
      });
      throw new Error("Mapbox API key not available");
    }

    // Load Mapbox API if not already loaded
    if (!window.mapboxgl) {
      await this.loadMapboxAPI();
    }

    mapboxgl.accessToken = this.accessToken;

    // Use saved settings or defaults
    const center = [config.lng, config.lat];
    const zoom = config.zoom;
    const bearing = config.rotation;

    this.map = new mapboxgl.Map({
      container: containerId,
      style: "mapbox://styles/mapbox/satellite-v9",
      center: center,
      zoom: zoom,
      pitch: 0,
      bearing: bearing, // Set saved rotation
      projection: "mercator",
      pitchWithRotate: false,
      dragRotate: true,
      touchZoomRotate: true,
    });

    console.log("Mapbox initialized with settings:", { center, zoom, bearing });

    // Add navigation controls with compass for rotation
    this.map.addControl(
      new mapboxgl.NavigationControl({
        showCompass: true,
        showZoom: true,
      }),
    );

    // Prevent any pitch changes to maintain orthographic view
    this.map.on("pitch", () => {
      if (this.map.getPitch() > 0) {
        this.map.setPitch(0);
      }
    });

    document.body.className = "mapbox-active";
  }

  async loadMapboxAPI() {
    return new Promise((resolve, reject) => {
      if (window.mapboxgl) {
        resolve();
        return;
      }

      // Load CSS
      const link = document.createElement("link");
      link.href = "https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css";
      link.rel = "stylesheet";
      document.head.appendChild(link);

      // Load JS
      const script = document.createElement("script");
      script.src = "https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js";
      script.async = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  moveToLocation(input) {
    if (!input.trim()) return;

    const coords = this.parseCoordinates(input);
    if (coords) {
      this.map.flyTo({
        center: [coords.lng, coords.lat],
        zoom: this.map.getZoom(),
      });
      return;
    }

    // Use Mapbox geocoding
    const geocodingUrl = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(input)}.json?access_token=${this.accessToken}`;

    fetch(geocodingUrl)
      .then((response) => response.json())
      .then((data) => {
        if (data.features && data.features.length > 0) {
          const [lng, lat] = data.features[0].center;
          this.map.flyTo({ center: [lng, lat], zoom: this.map.getZoom() });
        } else {
          alert("Location not found");
        }
      })
      .catch((error) => {
        console.error("Geocoding error:", error);
        alert("Error finding location");
      });
  }

  generateBounds() {
    const bounds = this.map.getBounds();
    if (!bounds) return;

    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    const scale = this.calculateScale(center.lat, zoom);

    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();
    const nw = bounds.getNorthWest();
    const se = bounds.getSouthEast();

    // Populate the scale field in the form
    const scaleField = document.getElementById("id_scale");
    if (scaleField) {
      scaleField.value = scale.toFixed(2);
    }

    // Populate map_corners_lla field with corners in the expected format
    // Expected order: starting from the bottom-left corner counterclockwise
    // Format: [ [lat1, lon1, alt1], [lat2, lon2, alt2], [lat3, lon3, alt3], [lat4, lon4, alt4] ]
    const mapCornersField = document.getElementById("id_map_corners_lla");
    if (mapCornersField) {
      const cornersLLA = [
        [sw.lat, sw.lng, 0], // SW (bottom-left)
        [nw.lat, nw.lng, 0], // NW (top-left)
        [ne.lat, ne.lng, 0], // NE (top-right)
        [se.lat, se.lng, 0], // SE (bottom-right)
      ];
      mapCornersField.value = JSON.stringify(cornersLLA);

      const outputLlaField = document.getElementById("id_output_lla");
      if (outputLlaField) {
        outputLlaField.value = "True";
      }
    }

    this.generateSnapshot();
  }

  generateSnapshot() {
    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    const bearing = this.map.getBearing();
    const pitch = 0;

    const width = 1280;
    const height = 1280;

    const url = `https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/${center.lng},${center.lat},${zoom},${bearing},${pitch}/${width}x${height}?access_token=${this.accessToken}`;

    // Create a temporary image to convert to canvas and get base64 data
    const tempImg = new Image();
    tempImg.crossOrigin = "anonymous";

    tempImg.onload = () => {
      // Create canvas to convert image to base64
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(tempImg, 0, 0);

      // Get base64 data
      const imageData = canvas.toDataURL("image/png");

      // Save to server
      this.saveSnapshotToServer(imageData);

      // Hide snapshot display elements
      document.getElementById("snapshot").style.display = "none";
      document.getElementById("stitchedSnapshot").style.display = "none";
    };

    tempImg.onerror = () => {
      console.error("Failed to load Mapbox static image");
    };

    tempImg.src = url;
  }

  prepareScreenshot() {
    const style = document.createElement("style");
    style.id = "hide-controls";
    style.textContent = `
      .mapboxgl-ctrl-top-right,
      .mapboxgl-ctrl-top-left,
      .mapboxgl-ctrl-bottom-right,
      .mapboxgl-ctrl-bottom-left {
        display: none !important;
      }
    `;
    document.head.appendChild(style);

    const msg = document.getElementById("screenshotMsg");
    msg.innerHTML =
      'Map controls are hidden. Please use your browser\'s screenshot tool to capture the map. <button onclick="mapManager.restoreControls()">Restore Controls</button>';
    msg.style.display = "block";

    document.getElementById("map").scrollIntoView({ behavior: "smooth" });
  }

  restoreControls() {
    const style = document.getElementById("hide-controls");
    if (style) {
      style.remove();
    }
    document.getElementById("screenshotMsg").style.display = "none";
  }

  getBounds() {
    return this.map.getBounds();
  }

  getCenter() {
    return this.map.getCenter();
  }

  getZoom() {
    return this.map.getZoom();
  }

  async saveSnapshotToServer(imageData) {
    try {
      console.log("Saving snapshot to server...");

      // Get CSRF token
      const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");

      if (!csrfToken) {
        console.error("CSRF token not found");
        return;
      }

      console.log("Image data length:", imageData.length);
      console.log("Image data preview:", imageData.substring(0, 50));

      const formData = new FormData();
      formData.append("image_data", imageData);
      formData.append("csrfmiddlewaretoken", csrfToken.value);

      const response = await fetch("/api/v1/save-geospatial-snapshot/", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken.value,
        },
        body: formData,
      });

      console.log("Response status:", response.status);

      if (response.ok) {
        const result = await response.json();
        console.log("Server response:", result);

        if (result.success) {
          // Update the map field with the generated filename
          const mapField = document.getElementById("id_map");
          if (mapField) {
            // Hide the file input and show the generated filename instead
            mapField.style.display = "none";

            // Create a display element to show the generated file
            let fileDisplay = document.getElementById("generated-map-display");
            if (!fileDisplay) {
              fileDisplay = document.createElement("div");
              fileDisplay.id = "generated-map-display";
              fileDisplay.className = "alert alert-success";
              mapField.parentNode.appendChild(fileDisplay);
            }
            fileDisplay.innerHTML = `Generated map: ${result.filename}`;
            fileDisplay.style.display = "block";

            // Add a hidden input with the filename for form submission
            let hiddenInput = document.getElementById("generated-map-filename");
            if (!hiddenInput) {
              hiddenInput = document.createElement("input");
              hiddenInput.type = "hidden";
              hiddenInput.id = "generated-map-filename";
              hiddenInput.name = "generated_map_filename";
              mapField.parentNode.appendChild(hiddenInput);
            }
            hiddenInput.value = result.filename;

            // Set map_type to geospatial_map when generating a geospatial map
            const mapTypeField = document.getElementById("id_map_type");
            if (mapTypeField) {
              mapTypeField.value = "geospatial_map";
            }

            // Save current map settings to form fields
            if (window.saveCurrentMapSettings) {
              window.saveCurrentMapSettings();
            }
          }

          console.log(
            "Geospatial snapshot saved successfully:",
            result.filename,
          );
        } else {
          console.error("Failed to save snapshot:", result.error);
        }
      } else {
        const errorText = await response.text();
        console.error(
          "Server error saving snapshot:",
          response.status,
          errorText,
        );
      }
    } catch (error) {
      console.error("Error saving snapshot to server:", error);
    }
  }
}
