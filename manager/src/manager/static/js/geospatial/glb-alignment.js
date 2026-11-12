// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/* global module */

"use strict";

const MOVING_OPACITY = 0.25;
const DEFAULT_OPACITY = 0.6;
const SAVED_OPACITY = 1;
const FRAME_APPLIED = "#2e7d32";
const FRAME_UNAPPLIED = "#c62828";
const GLB_ACCEPTED_VIEW_KEY = "glbAcceptedView";
const MAP_EMPTY_HINT =
  "Set the map location and save the scene before aligning a 3D model.";
const PREVIEW_MISSING_HINT =
  "The preview of the saved 3D model could not be generated.";

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

// Capped below 360 so the heading never wraps to 0 at the slider end.
function clampHeading(v) {
  const num = Number(v);
  return isFinite(num) ? Math.min(359.9, Math.max(0, num)) : null;
}

function dragAnchor(anchor, grab, cur) {
  return {
    lat: Math.max(-85, Math.min(85, anchor.lat + (cur.lat - grab.lat))),
    lng: anchor.lng + (cur.lng - grab.lng),
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

const byId = (id) => document.getElementById(id);
const on = (el, type, fn, cap) => el.addEventListener(type, fn, cap === true);

class GlbAlignment {
  constructor() {
    const row = byId("glbAlignRow");
    if (!row) return;

    this.sceneId = row.dataset.sceneId;
    this.staged = null;
    this.saved = null;
    this.anchor = null;
    this.opacity = DEFAULT_OPACITY;
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
      controls: byId("glbAlignControls"),
      opacity: byId("glbOpacity"),
      headingNumber: byId("glbHeadingNumber"),
      headingRange: byId("glbHeadingRange"),
      footprint: byId("glbFootprint"),
      status: byId("glbAlignStatus"),
      accept: byId("glbAccept"),
      acceptWrap: byId("glbAcceptWrap"),
      reset: byId("glbReset"),
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
    on(this.ui.opacity, "input", (e) => {
      this.opacity = parseFloat(e.target.value);
      this._strategy().setOverlayOpacity(this.opacity);
    });

    const updateHeading = (e) => {
      const h = clampHeading(e.target.value);
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

    if (this.ui.savePosBtn)
      on(this.ui.savePosBtn, "click", () => this._savePosition());
    if (this.ui.removeBtn) on(this.ui.removeBtn, "click", () => this._remove());
    if (this.ui.useCheckbox)
      on(this.ui.useCheckbox, "change", () => this._toggleUse());

    for (const type of ["pointerdown", "mousedown", "touchstart"])
      on(this.ui.map, type, (e) => this._handleMapPointerDown(e), true);

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
    this.ui.accept.disabled = busy;
    this.ui.accept.style.pointerEvents = busy ? "none" : "";
    this.ui.acceptWrap.title = hint;
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
      const data = await this._request(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        { method: "GET" },
      );
      if (data.exists) {
        this.saved = data;
        this.anchor = { ...data.anchor };
        this._renderSavedBlock();
        this._drawSavedOverlay();
      }
    } catch (e) {}
  }

  _renderSavedBlock() {
    if (!this.ui.savedBlock || !this.saved) return;
    this.ui.savedFilename.textContent = this.saved.filename || "3D model";
    this.ui.downloadLink.href = this.saved.download_url;
    if (this.ui.useCheckbox) {
      this.ui.useCheckbox.checked = this.saved.use_glb_map || false;
    }
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

  _updateControlsVisibility() {
    if (!this.ui.savePosBtn) return;
    const show = !this.staged && !!this.saved && this.dirty;
    this.ui.savePosBtn.style.display = show ? "" : "none";
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
      : "Replace the saved 3D model with a new one? The saved model is kept until you accept the new one.";
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
      const data = await this._request(
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
      this.opacity = DEFAULT_OPACITY;
      this.dirty = false;
      this._updateInputs();
      this._updateSavedBlockVisibility();
      this.ui.controls.style.display = "";
      this._updateControlsVisibility();
      this.ui.footprint.textContent = `Footprint: ${this.staged.footprint.width.toFixed(1)} × ${this.staged.footprint.height.toFixed(1)} m`;

      const corners = buildOverlayCorners(this.anchor, this.staged.footprint);
      this._strategy().setOverlay(this.staged.imageUrl, corners, this.opacity);
      e.target.value = "";
    } catch (error) {
      this._showError(error.message);
    } finally {
      this.uploading = false;
      this._updateLocks();
    }
  }

  _updateInputs() {
    this.ui.headingNumber.value = this.anchor.heading_deg.toFixed(1);
    this.ui.headingRange.value = this.anchor.heading_deg;
    this.ui.opacity.value = this.opacity;
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
    if (!this.anchor) return;
    try {
      const strategy = this._strategy();
      const corners = this._corners();
      const base = this.staged ? this.opacity : SAVED_OPACITY;
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
    const grab = this._pointerLatLng(e);
    if (!pointInPolygon(grab, this._corners())) return;

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
    this.saving = true;
    this._updateLocks();

    try {
      await this._request(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        {
          method: "POST",
          body: {
            token: this.staged.token,
            anchor: this.anchor,
          },
        },
      );

      this.dirty = false;
      this._stashAcceptedView();
      this._strategy().removeOverlay();
      this.ui.status.textContent = "3D model saved; reloading...";
      setTimeout(() => window.location.reload(), 1000);
    } catch (error) {
      this.saving = false;
      this._updateLocks();
      this._showError(error.message);
    }
  }

  // Keeps the live view across the reload; the saved DB view would otherwise replace it.
  _stashAcceptedView() {
    try {
      window.saveCurrentMapSettings?.();
      window.sessionStorage.setItem(
        GLB_ACCEPTED_VIEW_KEY,
        JSON.stringify({
          path: window.location.pathname,
          provider: this.ui.mapProvider.value,
          settings: window.loadSavedGeospatialSettings?.() ?? {},
        }),
      );
    } catch (error) {
      console.error("Could not store the accepted map view:", error);
    }
  }

  _reset() {
    if (!this.staged && !this.saved) return;
    if (this.staged) {
      this.anchor = { ...this.staged.anchor };
    } else if (this.saved) {
      this.anchor = { ...this.saved.anchor };
    }
    this.opacity = DEFAULT_OPACITY;
    this.dirty = false;
    this._updateInputs();
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
    this.ui.controls.style.display = "none";
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
    this.ui.status.textContent = status;
  }

  async _savePosition() {
    if (!this.saved || !this.anchor) return;

    this.ui.status.textContent = "";
    this.saving = true;
    this._updateLocks();

    try {
      const sent = { ...this.anchor };
      const response = await this._request(
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
      const response = await this._request(
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
        ? "3D model applied to scene map"
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
      const response = await this._request(
        `/api/v1/scene/${encodeURIComponent(this.sceneId)}/geospatial-glb`,
        { method: "DELETE" },
      );

      this._applyServerState(response);
      this.saved = null;
      this.anchor = null;
      this.dirty = false;
      this._updateControlsVisibility();
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

  async _request(url, { method = "GET", body } = {}) {
    const headers = {};
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
    if (csrfToken) headers["X-CSRFToken"] = csrfToken.value;
    if (body && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    const response = await fetch(url, { method, headers, body });
    if (response.status === 204) return {};
    // Proxy errors (e.g. 413 from a front-end limit) are not JSON.
    const data = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }
}

// One-shot: read on the reload after accept. Only restores for the same page and map provider.
function takeGlbAcceptedView(provider) {
  try {
    const raw = window.sessionStorage.getItem(GLB_ACCEPTED_VIEW_KEY);
    window.sessionStorage.removeItem(GLB_ACCEPTED_VIEW_KEY);
    const stashed = raw ? JSON.parse(raw) : null;
    if (
      stashed?.path === window.location.pathname &&
      stashed.provider === provider
    ) {
      return stashed.settings;
    }
  } catch (error) {
    console.error("Could not read the accepted map view:", error);
  }
  return {};
}

if (typeof window !== "undefined") {
  window.takeGlbAcceptedView = takeGlbAcceptedView;
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
    dragAnchor,
    buildOverlayCorners,
  };
}
