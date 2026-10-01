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
    if (!bounds) {
      throw new Error(
        "Map bounds are not ready yet. Wait for the map to finish loading.",
      );
    }

    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    const heading =
      typeof this.map.getHeading === "function" ? this.map.getHeading() : 0;
    this.writeGeospatialFormFields(center.lat(), center.lng(), zoom, heading);

    this.generateSnapshot();
  }

  generateSnapshot() {
    const center = this.map.getCenter();
    const zoom = this.map.getZoom();

    const heading =
      typeof this.map.getHeading === "function" ? this.map.getHeading() : 0;
    const q = this.snapshotQuadrantCenters(
      center.lat(),
      center.lng(),
      zoom,
      heading,
    );
    const quadrants = [
      { name: "NW", ...q.NW },
      { name: "NE", ...q.NE },
      { name: "SW", ...q.SW },
      { name: "SE", ...q.SE },
    ];

    const snapPx = this.constructor.SNAPSHOT_SIZE_PX;
    let canvas = document.getElementById("stitchedSnapshot");
    if (!canvas) {
      canvas = document.createElement("canvas");
    }
    canvas.width = snapPx;
    canvas.height = snapPx;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      this.dispatchSnapshotResult({
        success: false,
        error: "Could not create map snapshot canvas",
      });
      return;
    }
    ctx.clearRect(0, 0, snapPx, snapPx);

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

          // Hide the snapshot display elements when present (legacy form only)
          canvas.style.display = "none";
          const snapshot = document.getElementById("snapshot");
          if (snapshot) {
            snapshot.style.display = "none";
          }
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
          const snapshot = document.getElementById("snapshot");
          if (snapshot) {
            snapshot.style.display = "none";
          }
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

      const csrfToken = this.getCsrfToken();

      if (!csrfToken) {
        console.error("CSRF token not found");
        this.dispatchSnapshotResult({
          success: false,
          error: "CSRF token not found",
        });
        return;
      }

      console.log("Image data length:", imageData.length);
      console.log("Image data preview:", imageData.substring(0, 50));

      const formData = new FormData();
      formData.append("image_data", imageData);
      formData.append("csrfmiddlewaretoken", csrfToken);

      const response = await fetch("/api/v1/save-geospatial-snapshot/", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
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
            if (!fileDisplay && mapField.parentNode) {
              fileDisplay = document.createElement("div");
              fileDisplay.id = "generated-map-display";
              fileDisplay.className = "alert alert-success";
              mapField.parentNode.appendChild(fileDisplay);
            }
            if (fileDisplay) {
              fileDisplay.innerHTML = `Generated map: ${result.filename}`;
              fileDisplay.style.display = "block";
            }
          }

          // Always expose filename for React picker / form bridges
          let hiddenInput = document.getElementById("generated-map-filename");
          if (!hiddenInput) {
            hiddenInput = document.createElement("input");
            hiddenInput.type = "hidden";
            hiddenInput.id = "generated-map-filename";
            hiddenInput.name = "generated_map_filename";
            const host =
              document.getElementById("ss-geo-map-bridge") || document.body;
            host.appendChild(hiddenInput);
          }
          hiddenInput.value = result.filename;

          // Set map_type to geospatial_map when generating a geospatial map
          const mapTypeField = document.getElementById("id_map_type");
          if (mapTypeField) {
            mapTypeField.value = "geospatial_map";
            mapTypeField.dispatchEvent(new Event("change", { bubbles: true }));
          }
          const geoSection = document.getElementById("ss-form-sec-geo");
          if (geoSection) {
            geoSection.open = true;
          }

          // Save current map settings to form fields
          if (window.saveCurrentMapSettings) {
            window.saveCurrentMapSettings();
          }

          console.log(
            "Geospatial snapshot saved successfully:",
            result.filename,
          );
          window.dispatchEvent(
            new CustomEvent("ss-geospatial-snapshot", {
              detail: {
                success: true,
                filename: result.filename,
                mediaUrl: result.media_url,
              },
            }),
          );
        } else {
          console.error("Failed to save snapshot:", result.error);
          window.dispatchEvent(
            new CustomEvent("ss-geospatial-snapshot", {
              detail: { success: false, error: result.error || "Save failed" },
            }),
          );
        }
      } else {
        const errorText = await response.text();
        console.error(
          "Server error saving snapshot:",
          response.status,
          errorText,
        );
        window.dispatchEvent(
          new CustomEvent("ss-geospatial-snapshot", {
            detail: {
              success: false,
              error: "Server error saving snapshot",
            },
          }),
        );
      }
    } catch (error) {
      console.error("Error saving snapshot to server:", error);
      window.dispatchEvent(
        new CustomEvent("ss-geospatial-snapshot", {
          detail: {
            success: false,
            error: error && error.message ? error.message : "Snapshot failed",
          },
        }),
      );
    }
  }
}
