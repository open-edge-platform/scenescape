// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

// Google Maps Plugin Implementation
class GoogleMapsPlugin extends MapInterface {
  constructor() {
    super();
    this.map = null;
    this.geocoder = null;
    this.apiKey = this.getGoogleMapsApiKey();
    // Note: Don't show modal in constructor - wait for initialize()
    this.ORTHO_ZOOM_THRESHOLD = 18;
  }

  getGoogleMapsApiKey() {
    // Then try to get from JSON script block (CSP-compliant)
    const scriptElement = document.getElementById("google-maps-api-key");
    if (scriptElement) {
      try {
        return JSON.parse(scriptElement.textContent);
      } catch (e) {
        console.error("Error parsing Google Maps API key from JSON script:", e);
      }
    }

    return "";
  }

  async initialize(containerId, config = {}) {
    // Check if API key is still empty and try to get it again
    if (!this.apiKey) {
      this.apiKey = this.getGoogleMapsApiKey();
    }

    if (!this.apiKey) {
      this.showApiKeyModal({
        providerName: "Google Maps",
        envVarName: "GOOGLE_MAPS_API_KEY",
        signupUrl: "https://console.cloud.google.com/google/maps-apis/",
      });
      throw new Error("Google Maps API key not available");
    }

    // Load Google Maps API if not already loaded
    if (!window.google) {
      await this.loadGoogleMapsAPI();
    }

    this.geocoder = new google.maps.Geocoder();

    // Use saved settings or defaults
    const center = {
      lat: config.lat,
      lng: config.lng,
    };
    const zoom = config.zoom;
    const rotation = config.rotation;

    this.map = new google.maps.Map(document.getElementById(containerId), {
      center: center,
      zoom: zoom,
      mapTypeId: "satellite",
      rotateControl: true,
      streetViewControl: false,
      fullscreenControl: true,
      mapTypeControl: true,
      zoomControl: true,
      tilt: 0,
      heading: rotation, // Set saved rotation
    });

    console.log("Google Maps initialized with settings:", {
      center,
      zoom,
      rotation,
    });

    // Add zoom change listener to enforce orthographic view
    this.map.addListener("zoom_changed", () => {
      const currentZoom = this.map.getZoom();
      if (currentZoom >= this.ORTHO_ZOOM_THRESHOLD) {
        this.map.setTilt(0);
      }
    });

    // Add tilt change listener to prevent tilting at high zoom
    this.map.addListener("tilt_changed", () => {
      const currentZoom = this.map.getZoom();
      const currentTilt = this.map.getTilt();
      if (currentZoom >= this.ORTHO_ZOOM_THRESHOLD && currentTilt > 0) {
        this.map.setTilt(0);
      }
    });

    document.body.className = "google-maps-active";
  }

  async loadGoogleMapsAPI() {
    return new Promise((resolve, reject) => {
      if (window.google) {
        resolve();
        return;
      }

      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${this.apiKey}&libraries=places`;
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  moveToLocation(input) {
    if (!input.trim()) return;

    const coords = this.parseCoordinates(input);
    if (coords) {
      this.map.setCenter({ lat: coords.lat, lng: coords.lng });
      return;
    }

    // Use Google geocoding
    this.geocoder.geocode({ address: input }, (results, status) => {
      if (status === "OK" && results[0]) {
        this.map.setCenter(results[0].geometry.location);
      } else {
        alert("Location not found: " + status);
      }
    });
  }

  generateBounds() {
    const bounds = this.map.getBounds();
    if (!bounds) return;

    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    const scale = this.calculateScale(center.lat(), zoom);

    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();

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
        [sw.lat(), sw.lng(), 0], // SW (bottom-left)
        [ne.lat(), sw.lng(), 0], // NW (top-left)
        [ne.lat(), ne.lng(), 0], // NE (top-right)
        [sw.lat(), ne.lng(), 0], // SE (bottom-right)
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

    // Calculate bounds for stitched approach (4 quadrants)
    const bounds = this.map.getBounds();
    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();
    const centerLat = center.lat();
    const centerLng = center.lng();

    const latRange = ne.lat() - sw.lat();
    const lngRange = ne.lng() - sw.lng();
    const quarterLat = latRange / 4;
    const quarterLng = lngRange / 4;

    const quadrants = [
      {
        name: "NW",
        lat: centerLat + quarterLat,
        lng: centerLng - quarterLng,
        x: 0,
        y: 0,
      },
      {
        name: "NE",
        lat: centerLat + quarterLat,
        lng: centerLng + quarterLng,
        x: 640,
        y: 0,
      },
      {
        name: "SW",
        lat: centerLat - quarterLat,
        lng: centerLng - quarterLng,
        x: 0,
        y: 640,
      },
      {
        name: "SE",
        lat: centerLat - quarterLat,
        lng: centerLng + quarterLng,
        x: 640,
        y: 640,
      },
    ];

    const canvas = document.getElementById("stitchedSnapshot");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, 1280, 1280);

    let loadedImages = 0;
    const totalImages = 4;

    quadrants.forEach((quadrant) => {
      const img = new Image();
      img.crossOrigin = "anonymous";

      img.onload = () => {
        ctx.drawImage(img, quadrant.x, quadrant.y, 640, 640);
        loadedImages++;

        if (loadedImages === totalImages) {
          // Convert canvas to base64 PNG data
          const imageData = canvas.toDataURL("image/png");

          // Save the image to server and update map field
          this.saveSnapshotToServer(imageData);

          // Hide the snapshot display elements
          canvas.style.display = "none";
          document.getElementById("snapshot").style.display = "none";
        }
      };

      img.onerror = () => {
        console.error(`Failed to load quadrant ${quadrant.name}`);
        loadedImages++;

        if (loadedImages === totalImages) {
          // Even if some images failed, try to save what we have
          const imageData = canvas.toDataURL("image/png");
          this.saveSnapshotToServer(imageData);
          canvas.style.display = "none";
          document.getElementById("snapshot").style.display = "none";
        }
      };

      const url = `https://maps.googleapis.com/maps/api/staticmap?center=${quadrant.lat},${quadrant.lng}&zoom=${zoom}&size=640x640&maptype=satellite&key=${this.apiKey}&format=png`;
      img.src = url;
    });
  }

  prepareScreenshot() {
    // Hide all controls for Google Maps
    const style = document.createElement("style");
    style.id = "hide-controls";
    style.textContent = `
      .gm-style-cc,
      .gmnoprint {
        display: none !important;
      }
    `;
    document.head.appendChild(style);

    const msg = document.getElementById("screenshotMsg");
    msg.innerHTML =
      'Map controls are hidden. Please use your browser\'s screenshot tool to capture the map. <button type="button" id="restoreControlsBtn">Restore Controls</button>';
    msg.style.display = "block";

    // Add event listener to the restore button
    const restoreBtn = document.getElementById("restoreControlsBtn");
    if (restoreBtn) {
      restoreBtn.addEventListener("click", () => {
        this.restoreControls();
      });
    }

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
