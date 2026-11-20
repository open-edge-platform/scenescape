// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* global module, requestJson */

"use strict";

// Kept below 1 so the map stays visible through the overlay; order must be MOVING < DEFAULT < SAVED.
const MOVING_OPACITY = 0.3;
const DEFAULT_OPACITY = 0.7;
const SAVED_OPACITY = 0.7;
const DIAL_COARSE_KEY_DEG = 15;
// A drag within this many degrees of 0/90/180/270 lands on it; Shift turns snapping off.
const DIAL_CARDINAL_SNAP_DEG = 5;
// Shift-drag rotates the model by this fraction of the pointer's rotation.
const DIAL_FINE_RATIO = 0.25;
const DIAL_MIN_RADIUS_PX = 30;
const DIAL_MAX_RADIUS_PX = 70;
// The ring's diameter stays within 75% of the preview's shorter side, even when zoomed far out.
const DIAL_MAX_BOX_FRACTION = 0.375;
// Ring geometry and colors live in geospatial.css; the viewBox keeps the ring circular at any size.
const DIAL_RING_SVG =
  '<svg class="glb-rot-ring" viewBox="0 0 100 100" aria-hidden="true" focusable="false">' +
  '<circle class="glb-rot-hit" cx="50" cy="50" r="50"></circle>' +
  '<circle class="glb-rot-halo" cx="50" cy="50" r="50"></circle>' +
  '<circle class="glb-rot-line" cx="50" cy="50" r="50"></circle>' +
  '<path class="glb-rot-tick" d="M50 -5 V9"></path>' +
  '<path class="glb-rot-tick" d="M100 50 H92"></path>' +
  '<path class="glb-rot-tick" d="M50 100 V92"></path>' +
  '<path class="glb-rot-tick" d="M0 50 H8"></path>' +
  "</svg>";
const FRAME_APPLIED = "#2e7d32";
const FRAME_UNAPPLIED = "#c62828";
const MAP_EMPTY_HINT =
  "Set the map location and save the scene before aligning a 3D model.";
const PREVIEW_MISSING_HINT =
  "The preview of the saved 3D model could not be generated.";
// Keep equal to MAX_ANCHOR_DISTANCE_KM in manager/glb_alignment.py, which enforces it on save.
const FAR_ANCHOR_KM = 50;
const FAR_ANCHOR_HINT = `The 3D model must stay within ${FAR_ANCHOR_KM} km of the map center.`;
const BYTES_PER_MB = 1024 * 1024;

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

// Capped below 360 so the heading never wraps to 0 at the top of the range.
function clampHeading(v) {
  const num = Number(v);
  return isFinite(num) ? Math.min(359.9, Math.max(0, num)) : null;
}

function wrapHeading(deg) {
  return ((deg % 360) + 360) % 360;
}

// Clockwise from north (screen up), in [0, 360); center and pt are screen px.
function angleFromPointer(center, pt) {
  const rad = Math.atan2(pt.x - center.x, center.y - pt.y);
  return wrapHeading((rad * 180) / Math.PI);
}

// Signed shortest rotation from angle a to angle b, in (-180, 180].
function angleDelta(a, b) {
  const d = wrapHeading(b - a);
  return d > 180 ? d - 360 : d;
}

function snapToCardinal(heading, threshold = DIAL_CARDINAL_SNAP_DEG) {
  const nearest = Math.round(heading / 90) * 90;
  return Math.abs(heading - nearest) <= threshold
    ? wrapHeading(nearest)
    : heading;
}

// `raw` stays unsnapped between moves, so the snap never makes the dial sticky.
function dragHeading(raw, delta, fine) {
  const next = wrapHeading(raw + delta * (fine ? DIAL_FINE_RATIO : 1));
  return {
    raw: next,
    heading: clampHeading(fine ? next : snapToCardinal(next)),
  };
}

function dialRadius(widthPx, heightPx) {
  const size = Math.min(widthPx, heightPx);
  if (!isFinite(size)) return DIAL_MIN_RADIUS_PX;
  const radius = Math.min(
    DIAL_MAX_RADIUS_PX,
    Math.max(DIAL_MIN_RADIUS_PX, size * 0.3),
  );
  return Math.min(radius, size * DIAL_MAX_BOX_FRACTION);
}

function dragAnchor(anchor, grab, cur) {
  // Shortest signed longitude delta, so a drag across the antimeridian moves the anchor a short way
  const dLng = _wrapDegrees180(cur.lng - grab.lng);
  return {
    lat: Math.max(-85, Math.min(85, anchor.lat + (cur.lat - grab.lat))),
    lng: _wrapDegrees180(anchor.lng + dLng),
    heading_deg: anchor.heading_deg,
  };
}

function buildOverlayCorners(anchor, footprint) {
  return GeoOverlayMath.footprintCornersLLA(
    anchor.lat,
    anchor.lng,
    anchor.heading_deg,
    footprint.width,
    footprint.height,
  );
}

function distanceKm(a, b) {
  const EARTH_RADIUS_KM = 6371;
  const rad = (deg) => (deg * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

function formatMegabytes(bytes) {
  return `${Number((bytes / BYTES_PER_MB).toFixed(1))} MB`;
}

const byId = (id) => document.getElementById(id);
const on = (el, type, fn, cap) => el.addEventListener(type, fn, cap === true);

class GlbAlignment {
  constructor() {
    const row = byId("glbAlignRow");
    if (!row) return;

    this.sceneId = row.dataset.sceneId;
    this.maxUploadBytes = Number(row.dataset.maxUploadBytes) || 0;
    this.staged = null;
    this.saved = null;
    this.anchor = null;
    this.dial = null;
    this._unwatchMap = null;
    this._overlayDragging = false;
    this.dirty = false;
    this._isMoving = false;
    this.uploading = false;
    this.saving = false;
    this.mapReady = false;

    this.ui = {
      row,
      hint: byId("glbAlignHint"),
      file: byId("glbFileInput"),
      fileWrap: byId("glbFileWrap"),
      footprint: byId("glbFootprint"),
      status: byId("glbAlignStatus"),
      cancel: byId("glbCancel"),
      map: byId("map"),
      mapType: byId("id_map_type"),
      mapCenterLat: byId("id_map_center_lat"),
      mapCenterLng: byId("id_map_center_lng"),
      mapProvider: byId("mapProvider"),
      savedBlock: byId("glbSavedBlock"),
      savedFilename: byId("glbSavedFilename"),
      downloadLink: byId("glbDownloadLink"),
      removeBtn: byId("glbRemoveBtn"),
      useCheckbox: byId("glbUse"),
      savePosBtn: byId("glbSavePosition"),
      savePosWrap: byId("glbSavePositionWrap"),
    };

    window.addEventListener("geomap-ready", () => {
      this.mapReady = true;
      this._drawSavedOverlay();
      this._watchMap();
    });
    this._loadSavedAlignment();
    this._updateVisibility();

    on(this.ui.mapType, "change", () => this._updateVisibility());
    on(this.ui.mapProvider, "change", () => {
      if (this.staged)
        this._cancel("Map provider changed; upload the 3D model again.");
    });

    on(this.ui.file, "click", (e) => this._confirmReplaceStaged(e));
    on(this.ui.file, "change", (e) => this._handleFileUpload(e));

    on(this.ui.cancel, "click", () => this._cancel());

    if (this.ui.savePosBtn)
      on(this.ui.savePosBtn, "click", () => this._savePosition());
    if (this.ui.removeBtn) on(this.ui.removeBtn, "click", () => this._remove());
    if (this.ui.useCheckbox)
      on(this.ui.useCheckbox, "change", () => this._toggleUse());

    for (const type of ["pointerdown", "mousedown", "touchstart"])
      on(this.ui.map, type, (e) => this._handleMapPointerDown(e), true);
    on(this.ui.map, "pointermove", (e) => this._trackHover(e));
    on(this.ui.map, "pointerleave", () => this._setHover(false));

    window.addEventListener("beforeunload", (e) => {
      if (this.dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
    const form = row.closest("form");
    if (form)
      on(form, "submit", (event) => this._attachGlbChanges(form, event));
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
    this._syncDial();
    if (!isGeo) return;

    this._updateLocks();
    this.ui.hint.textContent = this._mapEmpty() ? MAP_EMPTY_HINT : "";
  }

  _updateLocks() {
    const busy = this.uploading || this.saving;
    let hint = "";
    if (this.saving) hint = "saving glb...";
    else if (this.uploading) hint = "loading glb...";

    this.ui.file.disabled = busy || this._mapEmpty();
    this.ui.file.style.pointerEvents = busy ? "none" : "";
    this.ui.fileWrap.title = hint;
    if (this.ui.savePosBtn) {
      this.ui.savePosBtn.disabled = busy;
      this.ui.savePosBtn.style.pointerEvents = busy ? "none" : "";
      this.ui.savePosWrap.title = hint;
    }
    if (this.ui.removeBtn) {
      this.ui.removeBtn.disabled = busy;
      this.ui.removeBtn.style.pointerEvents = busy ? "none" : "";
    }
    if (this.ui.useCheckbox) {
      this.ui.useCheckbox.disabled = busy;
    }
  }

  async _loadSavedAlignment() {
    try {
      const data = await requestJson(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        { method: "GET" },
      );
      if (data.exists) {
        this.saved = data;
        this.anchor = { ...data.anchor };
        this._renderSavedBlock();
        this._drawSavedOverlay();
        this._updateFarAnchorHint();
      }
    } catch (e) {
      console.error("Failed to load the saved 3D model:", e);
      this._showError(`Could not load the saved 3D model: ${e.message}`);
    }
  }

  _isFarFromCenter(anchor) {
    if (this._mapEmpty()) return false;
    const center = {
      lat: parseFloat(this.ui.mapCenterLat.value),
      lng: parseFloat(this.ui.mapCenterLng.value),
    };
    return distanceKm(anchor, center) > FAR_ANCHOR_KM;
  }

  _updateFarAnchorHint() {
    const far = !!this.anchor && this._isFarFromCenter(this.anchor);
    if (far) this.ui.hint.textContent = FAR_ANCHOR_HINT;
    else if (this.ui.hint.textContent === FAR_ANCHOR_HINT)
      this.ui.hint.textContent = this._mapEmpty() ? MAP_EMPTY_HINT : "";
  }

  _renderSavedBlock() {
    if (!this.ui.savedBlock || !this.saved) return;
    this.ui.savedFilename.textContent = this.saved.filename || "3D model";
    this.ui.downloadLink.href = this.saved.download_url;
    if (this.ui.useCheckbox) {
      this.ui.useCheckbox.checked = this.saved.use_glb_map || false;
    }
    this._updateFarAnchorHint();
    this._updateSavedBlockVisibility();
    this._updateControlsVisibility();
  }

  // The saved block is hidden while a replacement is staged, so only one state shows.
  _updateSavedBlockVisibility() {
    if (!this.ui.savedBlock) return;
    this.ui.savedBlock.style.display = this.saved && !this.staged ? "" : "none";
  }

  _frameColor() {
    return this.saved?.use_glb_map ? FRAME_APPLIED : FRAME_UNAPPLIED;
  }

  // Cancel and the footprint belong to a staged GLB; Save position to a moved saved GLB.
  _updateControlsVisibility() {
    this._syncDial();
    const footprint = this.staged?.footprint;
    this.ui.footprint.textContent = footprint
      ? `Footprint: ${footprint.width.toFixed(1)} × ${footprint.height.toFixed(1)} m`
      : "";
    this.ui.cancel.style.display = this.staged ? "" : "none";
    if (!this.ui.savePosBtn) return;
    const show = !this.staged && !!this.saved && this.dirty;
    this.ui.savePosBtn.style.display = show ? "" : "none";
  }

  _dialWanted() {
    return (
      !!this.anchor &&
      !this._overlayDragging &&
      !!(this.staged || this.saved) &&
      this.ui.mapType.value === "geospatial_map"
    );
  }

  _watchMap() {
    this._unwatchMap?.();
    this._unwatchMap = this._strategy().onViewChange(() => this._syncDial());
    this._syncDial();
  }

  // Dial center and ring radius in map-container px.
  _dialLayout() {
    const strategy = this._strategy();
    const corners = this._corners();
    if (corners.length < 3) return null;
    const [sw, se, ne] = corners.map((c) =>
      strategy.latLngToPoint(c.lat, c.lng),
    );
    const center = strategy.latLngToPoint(this.anchor.lat, this.anchor.lng);
    const radius = dialRadius(
      Math.hypot(se.x - sw.x, se.y - sw.y),
      Math.hypot(ne.x - se.x, ne.y - se.y),
    );
    return { x: center.x, y: center.y, radius };
  }

  _ensureDial() {
    if (!this.dial) {
      const root = document.createElement("div");
      root.className = "glb-rot-dial";
      root.innerHTML = DIAL_RING_SVG;
      const knob = document.createElement("div");
      knob.className = "glb-rot-knob";
      knob.tabIndex = 0;
      knob.setAttribute("role", "slider");
      knob.setAttribute("aria-label", "3D model heading");
      knob.setAttribute("aria-valuemin", "0");
      knob.setAttribute("aria-valuemax", "359.9");
      root.appendChild(knob);
      for (const type of ["pointerdown", "mousedown", "touchstart"])
        on(root, type, (e) => this._handleDialPointerDown(e));
      on(knob, "keydown", (e) => this._handleDialKey(e));
      on(knob, "focus", () => this._setDialFocused(true));
      on(knob, "blur", () => this._setDialFocused(false));
      this.dial = { root, knob };
    }
    // Switching map provider empties the map container, which detaches the dial.
    if (this.dial.root.parentNode !== this.ui.map)
      this.ui.map.appendChild(this.dial.root);
    return this.dial;
  }

  _syncDial() {
    let layout = null;
    if (this._dialWanted()) {
      try {
        layout = this._dialLayout();
      } catch {
        // The map or its projection is not ready; a later map view change redraws the dial.
      }
    }
    if (!layout) {
      if (this.dial) this.dial.root.style.display = "none";
      return;
    }

    const { root, knob } = this._ensureDial();
    const { x, y, radius } = layout;
    const heading = this.anchor.heading_deg;
    const rad = (heading * Math.PI) / 180;
    root.style.display = "";
    root.style.left = `${x - radius}px`;
    root.style.top = `${y - radius}px`;
    root.style.width = `${2 * radius}px`;
    root.style.height = `${2 * radius}px`;
    knob.style.left = `${radius + radius * Math.sin(rad)}px`;
    knob.style.top = `${radius - radius * Math.cos(rad)}px`;
    knob.setAttribute("aria-valuenow", heading.toFixed(1));
    knob.setAttribute("aria-valuetext", `${heading.toFixed(1)} degrees`);
    root.classList.toggle(
      "glb-rot-dial--active",
      this._hover || this._dialDragging || this._dialFocused,
    );
  }

  _setHover(hover) {
    if (this._hover === hover) return;
    this._hover = hover;
    this._syncDial();
  }

  _setDialFocused(focused) {
    this._dialFocused = focused;
    this._syncDial();
  }

  _trackHover(e) {
    if (!this.anchor) return;
    let inside = false;
    try {
      inside = pointInPolygon(this._pointerLatLng(e), this._corners());
    } catch {
      // The map projection is not ready; the pointer cannot be over the preview yet.
    }
    this._setHover(inside);
  }

  _setHeading(heading) {
    this.anchor.heading_deg = heading;
    this.dirty = true;
    this._render();
  }

  _handleDialPointerDown(e) {
    e.stopPropagation();
    if (e.type !== "pointerdown" || !this.anchor || e.button > 0) return;
    e.preventDefault();

    let center;
    try {
      const rect = this.ui.map.getBoundingClientRect();
      const p = this._dialLayout();
      center = { x: rect.left + p.x, y: rect.top + p.y };
    } catch {
      return;
    }
    e.target.setPointerCapture?.(e.pointerId);
    const at = (ev) => ({ x: ev.clientX, y: ev.clientY });
    let raw = this.anchor.heading_deg;
    let last = angleFromPointer(center, at(e));
    const move = (ev) => {
      const angle = angleFromPointer(center, at(ev));
      const next = dragHeading(raw, angleDelta(last, angle), ev.shiftKey);
      raw = next.raw;
      last = angle;
      this._setHeading(next.heading);
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      this._dialDragging = false;
      this._endMove();
    };
    this._dialDragging = true;
    this._beginMove();
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  _handleDialKey(e) {
    const dir = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[
      e.key
    ];
    if (!dir || !this.anchor) return;
    e.preventDefault();
    const step = e.shiftKey ? DIAL_COARSE_KEY_DEG : 1;
    this._setHeading(
      clampHeading(wrapHeading(this.anchor.heading_deg + dir * step)),
    );
  }

  _drawSavedOverlay() {
    if (!this.mapReady || this.staged) return;
    if (!this.saved || !this.saved.anchor || !this.saved.footprint_m) return;
    if (!this.saved.preview_url) {
      this.ui.status.textContent = PREVIEW_MISSING_HINT;
      return;
    }
    try {
      const corners = buildOverlayCorners(
        this.saved.anchor,
        this.saved.footprint_m,
      );
      this._strategy().setOverlay(
        this.saved.preview_url,
        corners,
        SAVED_OPACITY,
        this._frameColor(),
      );
    } catch (e) {
      console.error("Failed to draw saved overlay:", e);
    }
  }

  _confirmReplaceStaged(e) {
    if (!this.staged && !this.saved) return;

    const msg = this.staged
      ? "Discard the staged 3D model and choose a new one?"
      : "Replace the saved 3D model with a new one? The saved model is kept until you save the new one.";
    if (!window.confirm(msg)) {
      e.preventDefault();
      return;
    }
    if (this.staged) this._cancel();
  }

  async _handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    this.ui.status.textContent = "";
    this.uploading = true;
    this._updateLocks();

    try {
      if (this._mapEmpty()) throw new Error(MAP_EMPTY_HINT);

      const form = new FormData();
      form.append("file", file);
      const data = await requestJson(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb-preview`,
        { method: "POST", body: form },
      );

      const startAnchor = this.saved?.anchor || data.anchor;
      this.staged = {
        token: data.token,
        imageUrl: data.preview_url,
        footprint: data.footprint_m,
        anchor: { ...startAnchor },
      };

      this.anchor = { ...startAnchor };
      this.dirty = false;
      this._updateFarAnchorHint();
      this._updateSavedBlockVisibility();
      this._updateControlsVisibility();

      const corners = buildOverlayCorners(this.anchor, this.staged.footprint);
      this._strategy().setOverlay(
        this.staged.imageUrl,
        corners,
        DEFAULT_OPACITY,
      );
      e.target.value = "";
    } catch (error) {
      this._showError(this._uploadErrorMessage(error));
    } finally {
      this.uploading = false;
      this._updateLocks();
    }
  }

  // A proxy 413 has no JSON body, so the limit comes from the template, which reads it from the server.
  _uploadErrorMessage(error) {
    if (error.status !== 413 || !(this.maxUploadBytes > 0))
      return error.message;
    return `The 3D model is too large. The upload limit is ${formatMegabytes(this.maxUploadBytes)}.`;
  }

  _corners() {
    const footprint = this.staged
      ? this.staged.footprint
      : this.saved?.footprint_m;
    if (!footprint) return [];
    return buildOverlayCorners(this.anchor, footprint);
  }

  _render() {
    this._updateControlsVisibility();
    this._updateFarAnchorHint();
    if (!this.anchor) return;
    try {
      const strategy = this._strategy();
      const corners = this._corners();
      const base = this.staged ? DEFAULT_OPACITY : SAVED_OPACITY;
      const opacity = this._isMoving ? Math.min(base, MOVING_OPACITY) : base;
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
    if (!this.anchor) return;
    // The dial sits inside #map, so its drags must not start an overlay drag.
    if (e.target && this.dial?.root.contains(e.target)) return;
    const grab = this._pointerLatLng(e);
    const inside = pointInPolygon(grab, this._corners());
    this._setHover(inside);
    if (!inside) return;

    e.preventDefault();
    e.stopPropagation();
    if (e.type !== "pointerdown") return;

    const anchor0 = { ...this.anchor };
    const move = (ev) => {
      const next = dragAnchor(anchor0, grab, this._pointerLatLng(ev));
      if (this._isFarFromCenter(next)) {
        this.ui.hint.textContent = FAR_ANCHOR_HINT;
        return;
      }
      this.anchor = next;
      this.dirty = true;
      this._render();
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      this._overlayDragging = false;
      this._endMove();
    };
    // The dial hides while the overlay is held so it does not cover the map underneath.
    this._overlayDragging = true;
    this._beginMove();
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  // Renders at once so a press without a drag already shows the map underneath.
  _beginMove() {
    this._isMoving = true;
    this._render();
  }

  _endMove() {
    this._isMoving = false;
    this._render();
  }

  // Renders an error like Django form errors: a ul.errorlist with one li.
  _showError(message) {
    const list = document.createElement("ul");
    list.className = "errorlist";
    const item = document.createElement("li");
    item.textContent = message;
    list.appendChild(item);
    this.ui.status.replaceChildren(list);
  }

  _cancel(status = "") {
    try {
      this._strategy().removeOverlay();
    } catch (e) {}
    this.staged = null;
    if (this.saved) {
      this.anchor = { ...this.saved.anchor };
      this._drawSavedOverlay();
    } else {
      this.anchor = null;
    }
    this.dirty = false;
    this._updateSavedBlockVisibility();
    this._updateControlsVisibility();
    this._updateFarAnchorHint();
    this.ui.status.textContent = status;
  }

  async _savePosition() {
    if (!this.saved || !this.anchor) return;

    this.ui.status.textContent = "";
    this.saving = true;
    this._updateLocks();

    try {
      const sent = { ...this.anchor };
      const response = await requestJson(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        {
          method: "PUT",
          body: { anchor: sent },
        },
      );

      this.saved.anchor = sent;
      this.saved.preview_url = response.preview_url ?? null;
      this._applyServerState(response);
      this.dirty = JSON.stringify(this.anchor) !== JSON.stringify(sent);
      this._updateControlsVisibility();
      this.ui.status.textContent = "Position saved";
    } catch (error) {
      this._showError(error.message);
    } finally {
      this.saving = false;
      this._updateLocks();
    }
  }

  // Mirrors the state of a server-side GLB write into the scene-edit form: the values it changed
  // and the state token that Save Scene Updates posts back to detect an out-of-date page.
  _applyServerState(response) {
    this._applySceneFields(response?.scene_fields);
    const token = byId("id_glb_state_token");
    if (token && response?.state_token) token.value = response.state_token;
  }

  // Mirrors server-side GLB changes (pose, scale, corners) into the scene-edit form so that
  // Save Scene Updates does not post the values from before the change.
  _applySceneFields(fields) {
    if (!fields) return;
    for (const [name, value] of Object.entries(fields)) {
      const input = byId(`id_${name}`);
      if (!input) continue;
      if (name === "map_corners_lla") {
        input.value = value ? JSON.stringify(value) : "";
      } else {
        input.value = value ?? "";
      }
    }
  }

  // Save Scene Updates carries a staged GLB (token + anchor) or a shifted saved anchor;
  // SceneUpdateView.form_valid persists them.
  _attachGlbChanges(form, event) {
    if (this.saving) {
      // A GLB request is in flight; submitting now would post pre-change values.
      event.preventDefault();
      this.ui.status.textContent =
        "Wait for the 3D model change to finish, then save.";
      return;
    }
    form.querySelector('input[name="glb_token"]')?.remove();
    form.querySelector('input[name="glb_anchor"]')?.remove();
    if (!this.anchor || this.ui.mapType.value !== "geospatial_map") return;

    const fields = [];
    if (this.staged) {
      fields.push(["glb_token", this.staged.token]);
    } else if (!this.saved || !this.dirty) {
      return;
    }
    fields.push(["glb_anchor", JSON.stringify(this.anchor)]);

    for (const [name, value] of fields) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }
    // The submit navigates away, so the unsaved-changes prompt must not fire.
    this.dirty = false;
  }

  async _toggleUse() {
    if (!this.saved || !this.ui.useCheckbox) return;

    this.ui.status.textContent = "";
    this.saving = true;
    this._updateLocks();

    try {
      const response = await requestJson(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        {
          method: "PUT",
          body: { use_glb_map: this.ui.useCheckbox.checked },
        },
      );

      this.saved.use_glb_map = response.use_glb_map;
      this.saved.preview_url = response.preview_url ?? null;
      this._applyServerState(response);
      // The overlay is redrawn from the response so its frame always matches the applied state.
      this._drawSavedOverlay();
      this.ui.status.textContent = this.saved.use_glb_map
        ? "3D model shown on scene map"
        : "3D model overlay only";
    } catch (error) {
      this.ui.useCheckbox.checked = this.saved.use_glb_map || false;
      this._showError(error.message);
    } finally {
      this.saving = false;
      this._updateLocks();
    }
  }

  async _remove() {
    if (!this.saved) return;

    const msg = `Remove the saved 3D model "${this.saved.filename || "3D model"}"? This cannot be undone.`;
    if (!window.confirm(msg)) return;

    this.ui.status.textContent = "";
    this.saving = true;
    this._updateLocks();

    try {
      const response = await requestJson(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        { method: "DELETE" },
      );

      this._applyServerState(response);
      this.saved = null;
      this.anchor = null;
      this.dirty = false;
      this._updateControlsVisibility();
      this._updateFarAnchorHint();
      this._updateSavedBlockVisibility();
      this._strategy().removeOverlay();
      this.ui.status.textContent = "3D model removed";
    } catch (error) {
      this._showError(error.message);
    } finally {
      this.saving = false;
      this._updateLocks();
    }
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
    clampHeading,
    angleFromPointer,
    angleDelta,
    snapToCardinal,
    dragHeading,
    dialRadius,
    dragAnchor,
    buildOverlayCorners,
    distanceKm,
    MOVING_OPACITY,
    DEFAULT_OPACITY,
    SAVED_OPACITY,
  };
}
