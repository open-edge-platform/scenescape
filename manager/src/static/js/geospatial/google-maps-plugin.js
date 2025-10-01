"use strict";

// Google Maps Plugin Implementation
class GoogleMapsPlugin extends MapInterface {
  constructor() {
    super();
    this.map = null;
    this.geocoder = null;
    this.apiKey = "AIzaSyD0tU-s_bUJpcKTHSb1Ah64v7ZOcpezlM0"; //"<API_KEY>";
    this.ORTHO_ZOOM_THRESHOLD = 18;
  }

  async initialize(containerId, config = {}) {
    // Load Google Maps API if not already loaded
    if (!window.google) {
      await this.loadGoogleMapsAPI();
    }

    this.geocoder = new google.maps.Geocoder();
    this.map = new google.maps.Map(document.getElementById(containerId), {
      center: { lat: config.lat || 37.7749, lng: config.lng || -122.4194 },
      zoom: config.zoom || 15,
      mapTypeId: "satellite",
      rotateControl: true,
      streetViewControl: false,
      fullscreenControl: true,
      mapTypeControl: true,
      zoomControl: true,
      tilt: 0,
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
    const scale = this.calculateScale(center.lat(), zoom, 1280);

    const ne = bounds.getNorthEast();
    const sw = bounds.getSouthWest();
    const corners = [
      { name: "NE", lat: ne.lat(), lng: ne.lng(), alt: 0 },
      { name: "NW", lat: ne.lat(), lng: sw.lng(), alt: 0 },
      { name: "SW", lat: sw.lat(), lng: sw.lng(), alt: 0 },
      { name: "SE", lat: sw.lat(), lng: ne.lng(), alt: 0 },
    ];

    this.displayBoundsOutput(corners, scale, zoom);

    // Populate the scale field in the form
    const scaleField = document.getElementById("id_scale");
    if (scaleField) {
      scaleField.value = scale.toFixed(2);
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
          canvas.style.display = "block";
          document.getElementById("snapshot").style.display = "none";
        }
      };

      img.onerror = () => {
        console.error(`Failed to load quadrant ${quadrant.name}`);
        loadedImages++;
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
}
