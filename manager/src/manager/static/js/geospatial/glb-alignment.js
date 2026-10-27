// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* global module */

"use strict";

const MOVING_OPACITY = 0.25;
const DEFAULT_OPACITY = 0.6;
const MAP_EMPTY_HINT =
  "Set the map location and save the scene before aligning a 3D model.";

function pointInPolygon(pt, corners) {
  const x = pt.lng;
  const y = pt.lat;
  let inside = false;
  for (let i = 0, j = corners.length - 1; i < corners.length; j = i++) {
    const xi = corners[i].lng;
    const yi = corners[i].lat;
    const xj = corners[j].lng;
    const yj = corners[j].lat;
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function normalizeHeading(v) {
  const num = Number(v);
  return isFinite(num) ? ((num % 360) + 360) % 360 : null;
}

function dragAnchor(anchor, grab, cur) {
  return {
    lat: Math.max(-85, Math.min(85, anchor.lat + (cur.lat - grab.lat))),
    lng: anchor.lng + (cur.lng - grab.lng),
    heading_deg: anchor.heading_deg,
  };
}

const byId = (id) => document.getElementById(id);
const on = (el, type, fn, cap) => el.addEventListener(type, fn, cap === true);

class GlbAlignment {
  constructor() {
    const row = byId("glbAlignRow");
    if (!row) return;

    this.sceneId = row.dataset.sceneId;
    this.staged = null;
    this.anchor = null;
    this.opacity = DEFAULT_OPACITY;
    this.savedAnchor = null;
    this.dirty = false;
    this._isMoving = false;

    this.ui = {
      row,
      hint: byId("glbAlignHint"),
      file: byId("glbFileInput"),
      controls: byId("glbAlignControls"),
      opacity: byId("glbOpacity"),
      headingNumber: byId("glbHeadingNumber"),
      headingRange: byId("glbHeadingRange"),
      footprint: byId("glbFootprint"),
      status: byId("glbAlignStatus"),
      accept: byId("glbAccept"),
      reset: byId("glbReset"),
      cancel: byId("glbCancel"),
      map: byId("map"),
      mapType: byId("id_map_type"),
      mapCenterLat: byId("id_map_center_lat"),
      mapCenterLng: byId("id_map_center_lng"),
      mapProvider: byId("mapProvider"),
    };

    this._loadSavedAlignment();
    this._updateVisibility();

    on(this.ui.mapType, "change", () => this._updateVisibility());
    on(this.ui.mapProvider, "change", () => {
      if (this.staged)
        this._cancel("Map provider changed; upload the 3D model again.");
    });

    on(this.ui.file, "change", (e) => this._handleFileUpload(e));
    on(this.ui.opacity, "input", (e) => {
      this.opacity = parseFloat(e.target.value);
      this._strategy().setOverlayOpacity(this.opacity);
    });

    const updateHeading = (e) => {
      const h = normalizeHeading(e.target.value);
      if (h !== null && this.anchor) {
        this.anchor.heading_deg = h;
        this.ui.headingNumber.value = h.toFixed(1);
        this.ui.headingRange.value = h;
        this.dirty = true;
        this._render();
      }
    };
    on(this.ui.headingNumber, "input", updateHeading);
    on(this.ui.headingRange, "input", updateHeading);
    on(this.ui.headingRange, "pointerdown", () => this._beginMove());
    on(this.ui.headingRange, "pointerup", () => this._endMove());

    on(this.ui.accept, "click", () => this._accept());
    on(this.ui.reset, "click", () => this._reset());
    on(this.ui.cancel, "click", () => this._cancel());

    for (const type of ["pointerdown", "mousedown", "touchstart"])
      on(this.ui.map, type, (e) => this._handleMapPointerDown(e), true);

    window.addEventListener("beforeunload", (e) => {
      if (this.dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }

  _strategy() {
    const m = window.mapManager?.getMapStrategy();
    if (!m) throw new Error("Map is not ready yet");
    return m;
  }

  _mapEmpty() {
    return !this.ui.mapCenterLat.value || !this.ui.mapCenterLng.value;
  }

  _updateVisibility() {
    const isGeo = this.ui.mapType.value === "geospatial_map";
    this.ui.row.style.display = isGeo ? "" : "none";
    if (!isGeo) return;

    this.ui.file.disabled = this._mapEmpty();
    this.ui.hint.textContent = this._mapEmpty() ? MAP_EMPTY_HINT : "";
  }

  async _loadSavedAlignment() {
    try {
      const data = await this._request(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        { method: "GET" },
      );
      this.savedAnchor = data.anchor;
    } catch (e) {}
  }

  async _handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    this.ui.status.textContent = "";

    try {
      if (this._mapEmpty()) throw new Error(MAP_EMPTY_HINT);

      const form = new FormData();
      form.append("file", file);
      const data = await this._request(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb-preview`,
        { method: "POST", body: form },
      );

      this.staged = {
        token: data.token,
        imageUrl: data.preview_url,
        footprint: data.footprint_m,
        existing: data.existing_content,
        startAnchor: this.savedAnchor || data.anchor,
      };

      this.anchor = { ...this.staged.startAnchor };
      this.opacity = DEFAULT_OPACITY;
      this.dirty = false;
      this._updateInputs();
      this.ui.controls.style.display = "";
      this.ui.footprint.textContent = `Footprint: ${this.staged.footprint.width.toFixed(1)} × ${this.staged.footprint.height.toFixed(1)} m`;

      const corners = this._corners();
      this._strategy().setOverlay(this.staged.imageUrl, corners, this.opacity);
      e.target.value = "";
    } catch (error) {
      this.ui.status.textContent = error.message;
    }
  }

  _updateInputs() {
    this.ui.headingNumber.value = this.anchor.heading_deg.toFixed(1);
    this.ui.headingRange.value = this.anchor.heading_deg;
    this.ui.opacity.value = this.opacity;
  }

  _corners() {
    return GeoOverlayMath.footprintCornersLLA(
      this.anchor.lat,
      this.anchor.lng,
      this.anchor.heading_deg,
      this.staged.footprint.width,
      this.staged.footprint.height,
    );
  }

  _render() {
    if (!this.staged || !this.anchor) return;
    try {
      const strategy = this._strategy();
      const corners = this._corners();
      const opacity = this._isMoving
        ? Math.min(this.opacity, MOVING_OPACITY)
        : this.opacity;
      strategy.updateOverlay(corners);
      strategy.setOverlayOpacity(opacity);
    } catch (e) {
      console.error("Render failed:", e);
    }
  }

  _pointerLatLng(e) {
    const rect = this.ui.map.getBoundingClientRect();
    const p = e.touches?.[0] ?? e;
    return this._strategy().pointToLatLng(
      p.clientX - rect.left,
      p.clientY - rect.top,
    );
  }

  _handleMapPointerDown(e) {
    if (!this.staged) return;
    const grab = this._pointerLatLng(e);
    if (!pointInPolygon(grab, this._corners())) return;

    // Inside the overlay: keep the map from panning (all three event types)
    e.preventDefault();
    e.stopPropagation();
    if (e.type !== "pointerdown") return;

    const anchor0 = { ...this.anchor };
    const move = (ev) => {
      this.anchor = dragAnchor(anchor0, grab, this._pointerLatLng(ev));
      this.dirty = true;
      this._render();
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      this._endMove();
    };
    this._beginMove();
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  _beginMove() {
    this._isMoving = true;
  }

  _endMove() {
    this._isMoving = false;
    this._render();
  }

  async _accept() {
    if (!this.staged || !this.anchor) return;

    this.ui.status.textContent = "";
    let ack = false;

    if (this.staged.existing) {
      const { cameras = 0, regions = 0, sensors = 0 } = this.staged.existing;
      if (cameras > 0 || regions > 0 || sensors > 0) {
        const msg = `This scene has ${cameras} camera(s), ${regions} region(s) and ${sensors} sensor(s). Placing the 3D model changes the scene's local coordinate frame under them and they are NOT re-based. Continue?`;
        ack = window.confirm(msg);
        if (!ack) return;
      }
    }

    try {
      await this._request(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        {
          method: "POST",
          body: {
            token: this.staged.token,
            anchor: this.anchor,
            acknowledge_frame_change: ack,
          },
        },
      );

      this.dirty = false;
      this._strategy().removeOverlay();
      this.ui.status.textContent = "3D model saved; reloading...";
      setTimeout(() => window.location.reload(), 1000);
    } catch (error) {
      this.ui.status.textContent = error.message;
    }
  }

  _reset() {
    if (!this.staged) return;
    this.anchor = { ...this.staged.startAnchor };
    this.opacity = DEFAULT_OPACITY;
    this.dirty = false;
    this._updateInputs();
    this._render();
  }

  _cancel(status = "") {
    try {
      this._strategy().removeOverlay();
    } catch (e) {}
    this.ui.controls.style.display = "none";
    this.staged = null;
    this.anchor = null;
    this.dirty = false;
    this.ui.status.textContent = status;
  }

  async _request(url, { method = "GET", body } = {}) {
    const headers = {};
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
    if (csrfToken) headers["X-CSRFToken"] = csrfToken.value;
    if (body && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    const response = await fetch(url, { method, headers, body });
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("glbAlignRow")) {
      window.glbAlignment = new GlbAlignment();
    }
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    GlbAlignment,
    pointInPolygon,
    normalizeHeading,
    dragAnchor,
  };
}
