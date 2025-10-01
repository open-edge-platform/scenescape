"use strict";

// Mapbox Plugin Implementation
class MapboxPlugin extends MapInterface {
  constructor() {
    super();
    this.map = null;
    this.accessToken =
      "pk.eyJ1Ijoic3BvbHVyaSIsImEiOiJjbWZvbXA1MjkwN2E1MnRwbHl0ZXJ2aThwIn0.xJRJl1GjEEGy90OIfDQbTw"; //"<ACCESS_TOKEN>";
  }

  async initialize(containerId, config = {}) {
    // Load Mapbox API if not already loaded
    if (!window.mapboxgl) {
      await this.loadMapboxAPI();
    }

    mapboxgl.accessToken = this.accessToken;

    this.map = new mapboxgl.Map({
      container: containerId,
      style: "mapbox://styles/mapbox/satellite-v9",
      center: [config.lng || -122.4194, config.lat || 37.7749],
      zoom: config.zoom || 15,
      pitch: 0,
      bearing: 0,
      projection: "mercator",
      pitchWithRotate: false,
      dragRotate: true,
      touchZoomRotate: true,
    });

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
    const scale = this.calculateScale(center.lat, zoom, 1280);

    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();
    const nw = bounds.getNorthWest();
    const se = bounds.getSouthEast();

    const corners = [
      { name: "NE", lat: ne.lat, lng: ne.lng, alt: 0 },
      { name: "NW", lat: nw.lat, lng: nw.lng, alt: 0 },
      { name: "SW", lat: sw.lat, lng: sw.lng, alt: 0 },
      { name: "SE", lat: se.lat, lng: se.lng, alt: 0 },
    ];

    this.displayBoundsOutput(corners, scale, zoom);
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

    const img = document.getElementById("snapshot");
    img.src = url;
    img.style.display = "block";

    document.getElementById("stitchedSnapshot").style.display = "none";
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
}
