// SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @file camcanvas.js
 * @description This file defines the CamCanvas class for displaying video frames.
 */

"use strict";

import {
  CALIBRATION_BACKGROUND_COLOR,
  CALIBRATION_POINT_COLORS,
  CALIBRATION_POINT_SCALE,
  CAMERA_SCALE_FACTOR,
  MAX_CALIBRATION_POINTS,
} from "/static/js/constants.js";

class CamCanvas {
  constructor(canvas, initialImageSrc) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.image = new Image();

    this.calibrationPoints = [];
    this.calibrationPointNames = [];
    for (let i = 0; i < MAX_CALIBRATION_POINTS; i++) {
      this.calibrationPointNames.push(`p${i}`);
    }
    this.calibrationPointSize = 0;

    this.camScaleFactor = CAMERA_SCALE_FACTOR;
    this.scale = 1;
    this.panX = 0;
    this.panY = 0;
    this.isPanning = false;
    this.isDragging = false;
    this.startX = 0;
    this.startY = 0;
    this.draggingPoint = null;
    this.calibrationUpdated = false;

    this.image.onload = () => {
      this.handleImageLoad();
    };

    this.initializeEventListeners();
    this.#observePaneResize();
    this.updateImageSrc(initialImageSrc);
  }

  getImageSize() {
    return [this.image.width, this.image.height];
  }

  initializeEventListeners() {
    this.canvas.addEventListener("mousedown", (event) =>
      this.onMouseDown(event),
    );
    this.canvas.addEventListener("mousemove", (event) =>
      this.onMouseMove(event),
    );
    this.canvas.addEventListener("mouseup", (event) => this.onMouseUp(event));
    this.canvas.addEventListener("mouseleave", (event) =>
      this.onMouseUp(event),
    );
    this.canvas.addEventListener("wheel", (event) => this.onWheel(event));
    this.canvas.addEventListener("dblclick", (event) => this.onDblClick(event));
    this.canvas.addEventListener("contextmenu", (event) =>
      this.onRightClick(event),
    );
  }

  #observePaneResize() {
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    this.resizeObserver = new ResizeObserver(() => {
      if (!this.image.width) {
        return;
      }
      this.#refitToPane();
    });
    this.resizeObserver.observe(this.canvas);
  }

  #paneSize() {
    return [this.canvas.clientWidth || 0, this.canvas.clientHeight || 0];
  }

  #computeFitScale() {
    const [paneW, paneH] = this.#paneSize();
    if (!paneW || !paneH || !this.image.width || !this.image.height) {
      return CAMERA_SCALE_FACTOR;
    }
    return Math.min(paneW / this.image.width, paneH / this.image.height);
  }

  #updatePointSize() {
    const [paneW, paneH] = this.#paneSize();
    const basis = Math.min(paneW || 1, paneH || 1);
    this.calibrationPointSize = (basis * CALIBRATION_POINT_SCALE) / this.scale;
  }

  #centerImage() {
    const [paneW, paneH] = this.#paneSize();
    const displayW = this.image.width * this.camScaleFactor * this.scale;
    const displayH = this.image.height * this.camScaleFactor * this.scale;
    this.panX = (paneW - displayW) / 2;
    this.panY = (paneH - displayH) / 2;
  }

  #refitToPane() {
    const [paneW, paneH] = this.#paneSize();
    if (!paneW || !paneH) {
      return;
    }
    const oldFactor = this.camScaleFactor;
    const oldW = this.canvas.width;
    const oldH = this.canvas.height;
    this.camScaleFactor = this.#computeFitScale();
    this.#updatePointSize();

    if (oldFactor > 0 && oldW > 0 && oldH > 0) {
      const ratio = this.camScaleFactor / oldFactor;
      this.panX = paneW / 2 - (oldW / 2 - this.panX) * ratio;
      this.panY = paneH / 2 - (oldH / 2 - this.panY) * ratio;
    } else {
      this.#centerImage();
    }
    this.drawImage();
  }

  #getImageCoordinates(x, y) {
    const mouseX = x - this.canvas.getBoundingClientRect().left;
    const mouseY = y - this.canvas.getBoundingClientRect().top;
    const imageX = (mouseX - this.panX) / (this.scale * this.camScaleFactor);
    const imageY = (mouseY - this.panY) / (this.scale * this.camScaleFactor);
    return [imageX, imageY];
  }

  // Find the calibration point that intersects with the given point
  #findPointIntersection(x, y) {
    const [imageX, imageY] = this.#getImageCoordinates(x, y);
    for (const point of this.calibrationPoints) {
      const distance = Math.sqrt(
        (point.x - imageX) ** 2 + (point.y - imageY) ** 2,
      );
      if (distance * this.camScaleFactor <= this.calibrationPointSize / 2) {
        return point;
      }
    }
    return null;
  }

  #isPointInBounds(x, y) {
    return x >= 0 && x < this.image.width && y >= 0 && y < this.image.height;
  }

  // Interaction Handlers

  onMouseDown(event) {
    this.startX = event.clientX - this.panX;
    this.startY = event.clientY - this.panY;

    const point = this.#findPointIntersection(event.clientX, event.clientY);
    if (point) {
      this.isDragging = true;
      this.draggingPoint = point;
    } else {
      this.isPanning = true;
    }
  }

  onMouseMove(event) {
    if (this.isPanning) {
      this.panX = event.clientX - this.startX;
      this.panY = event.clientY - this.startY;
      this.drawImage();
    } else if (this.isDragging) {
      [this.draggingPoint.x, this.draggingPoint.y] = this.#getImageCoordinates(
        event.clientX,
        event.clientY,
      );
      this.calibrationUpdated = true;
      this.drawImage();
    }
  }

  onMouseUp(event) {
    // Prevent context menu from appearing in edge browser
    event.preventDefault();

    this.isPanning = false;
    this.isDragging = false;
    this.draggingPoint = null;
  }

  onWheel(event) {
    event.preventDefault();
    // Define a constant zoom factor
    const zoomFactor = 1.1;
    const mouseX = event.clientX - this.canvas.getBoundingClientRect().left;
    const mouseY = event.clientY - this.canvas.getBoundingClientRect().top;

    const previousScale = this.scale;
    if (event.deltaY < 0) {
      // Zoom in
      this.scale *= zoomFactor;
    } else {
      // Zoom out
      this.scale /= zoomFactor;
    }
    // Prevent zooming out too much
    this.scale = Math.max(0.1, this.scale);

    // Calculate the scaling factor
    const scaleFactor = this.scale / previousScale;

    // Adjust pan values to keep the mouse position fixed
    this.panX = mouseX - (mouseX - this.panX) * scaleFactor;
    this.panY = mouseY - (mouseY - this.panY) * scaleFactor;

    this.#updatePointSize();
    this.drawImage();
  }

  onDblClick(event) {
    event.preventDefault();
    const [imageX, imageY] = this.#getImageCoordinates(
      event.clientX,
      event.clientY,
    );
    if (this.#isPointInBounds(imageX, imageY)) {
      this.addCalibrationPoint(imageX, imageY);
      this.drawImage();
    }
  }

  onRightClick(event) {
    event.preventDefault();

    const point = this.#findPointIntersection(event.clientX, event.clientY);
    if (point) {
      this.calibrationPoints = this.calibrationPoints.filter(
        (p) => p !== point,
      );
      this.calibrationPointNames.push(point.name);
      this.calibrationPointNames.sort((a, b) => {
        const numA = parseInt(a.replace(/\D/g, ""));
        const numB = parseInt(b.replace(/\D/g, ""));
        return numA - numB;
      });
      this.drawImage();
    }
  }

  // Image drawing functions

  drawImage() {
    const [width, height] = this.#paneSize();
    if (!width || !height) {
      return;
    }

    this.canvas.width = width;
    this.canvas.height = height;
    this.ctx.fillStyle = CALIBRATION_BACKGROUND_COLOR;
    this.ctx.fillRect(0, 0, width, height);

    if (!this.image.width || !this.image.height) {
      return;
    }

    const displayW = this.image.width * this.camScaleFactor;
    const displayH = this.image.height * this.camScaleFactor;

    this.ctx.save();
    this.ctx.translate(this.panX, this.panY);
    this.ctx.scale(this.scale, this.scale);
    this.ctx.drawImage(this.image, 0, 0, displayW, displayH);
    for (const point of this.calibrationPoints) {
      this.drawPoint(
        point.x * this.camScaleFactor,
        point.y * this.camScaleFactor,
        point.color,
        point.name,
      );
    }
    this.ctx.restore();
  }

  handleImageLoad() {
    const [paneW, paneH] = this.#paneSize();
    if (!paneW || !paneH) {
      requestAnimationFrame(() => this.handleImageLoad());
      return;
    }
    this.camScaleFactor = this.#computeFitScale();
    this.#updatePointSize();
    this.#centerImage();
    this.drawImage();
  }

  updateImageSrc(base64Image) {
    this.image.src = base64Image;
  }

  resetCameraView() {
    this.scale = 1;
    this.camScaleFactor = this.#computeFitScale();
    this.#updatePointSize();
    this.#centerImage();
    this.drawImage();
  }

  // Calibration Point functions

  drawPoint(x, y, color, name) {
    const size = this.calibrationPointSize;

    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.arc(x, y, size / 2, 0, Math.PI * 2);
    this.ctx.fill();

    this.ctx.font = `${Math.max(12, size)}px Arial`;
    this.ctx.fillStyle = "black";
    this.ctx.fillText(name, x + size / 2, y - size / 2);
  }

  addCalibrationPoint(x, y) {
    const name = this.calibrationPointNames.shift();
    const number = parseInt(name.replace(/\D/g, ""));
    this.calibrationPoints.push({
      x: x,
      y: y,
      color: CALIBRATION_POINT_COLORS[number % CALIBRATION_POINT_COLORS.length],
      name: name,
    });
    this.calibrationUpdated = true;
  }

  clearCalibrationPoints() {
    this.calibrationPoints = [];
    this.calibrationPointNames = [];
    for (let i = 0; i < MAX_CALIBRATION_POINTS; i++) {
      this.calibrationPointNames.push(`p${i}`);
    }
  }

  getCalibrationPoints() {
    return this.calibrationPoints
      .sort((a, b) => {
        const numA = parseInt(a.name.replace(/\D/g, ""));
        const numB = parseInt(b.name.replace(/\D/g, ""));
        return numA - numB;
      })
      .reduce((acc, point) => {
        acc[point.name] = [point.x, point.y];
        return acc;
      }, {});
  }
}

export { CamCanvas };
