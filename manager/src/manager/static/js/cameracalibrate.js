// SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @file cameracalibrate.js
 * @description This file defines the ConvergedCameraCalibration class, which provides
 * functions for managing the camera calibration process through a camera and a scene viewport
 */

"use strict";

import * as THREE from "/static/assets/three.module.js";
import { GLTFLoader } from "/static/examples/jsm/loaders/GLTFLoader.js";
import { CamCanvas } from "/static/js/camcanvas.js";
import { Viewport } from "/static/js/viewport.js";
import {
  APP_NAME,
  CMD_CAMERA,
  INITIAL_PROJECTION_OPACITY,
  MAX_COPLANAR_DETERMINANT,
  MAX_INTRINSICS_UPDATE_WAIT_TIME,
  FX,
  FY,
  CX,
  CY,
  K1,
  K2,
  P1,
  P2,
  K3,
  REST_URL,
} from "/static/js/constants.js";
import {
  compareIntrinsics,
  resizeRendererToDisplaySize,
  waitUntil,
} from "/static/js/utils.js";

(function bridgeAlertToParentToast() {
  if (window.__ssNativeAlert) {
    return;
  }
  window.__ssNativeAlert = window.alert.bind(window);
  window.alert = function (msg) {
    const text = String(msg);
    const parentToast =
      window.parent && window.parent !== window
        ? window.parent.ssToast
        : null;
    const toast =
      (window.ssToast && typeof window.ssToast.show === "function"
        ? window.ssToast
        : null) ||
      (parentToast && typeof parentToast.show === "function"
        ? parentToast
        : null);
    if (toast) {
      const bad =
        /fail|error|invalid|not found|unable|cannot|must|requires/i.test(
          text,
        ) && !/successfully|updated\. Ensure/i.test(text);
      const ok = /success|updated|Camera updated/i.test(text);
      toast.show(text, bad ? "bad" : ok ? "ok" : "info");
      return;
    }
    window.__ssNativeAlert(text);
  };
})();

/** Push live optics values to the React calibrate panel (embed only). */
function notifyParentCalibrationFields() {
  if (!window.parent || window.parent === window) {
    return;
  }
  if (!document.body.classList.contains("ss-embed")) {
    return;
  }
  const read = (name) => {
    const el = document.querySelector(`[name="${name}"]`);
    return el && "value" in el ? String(el.value) : "";
  };
  window.parent.postMessage(
    {
      type: "ss-calibrate-optics",
      intrinsics: {
        fx: read("intrinsics_fx"),
        fy: read("intrinsics_fy"),
        cx: read("intrinsics_cx"),
        cy: read("intrinsics_cy"),
      },
      distortion: {
        k1: read("distortion_k1"),
        k2: read("distortion_k2"),
        p1: read("distortion_p1"),
        p2: read("distortion_p2"),
        k3: read("distortion_k3"),
      },
    },
    window.location.origin,
  );
}

window.addEventListener("message", (ev) => {
  if (ev.origin !== window.location.origin) {
    return;
  }
  if (!ev.data || typeof ev.data !== "object") {
    return;
  }
  if (ev.data.type === "ss-calibrate-save-points") {
    const form = document.getElementById("calibration_form");
    if (form) {
      form.requestSubmit ? form.requestSubmit() : form.submit();
    }
    return;
  }
  if (ev.data.type === "ss-calibrate-request-pose") {
    try {
      const pose = window.ssCollectCalibrationPose
        ? window.ssCollectCalibrationPose()
        : null;
      window.parent.postMessage(
        {
          type: "ss-calibrate-pose",
          ok: Boolean(pose),
          ...(pose || { error: "no pose collector" }),
        },
        window.location.origin,
      );
    } catch (err) {
      window.parent.postMessage(
        {
          type: "ss-calibrate-pose",
          ok: false,
          error: err?.message || String(err),
        },
        window.location.origin,
      );
    }
    return;
  }
  if (ev.data.type === "ss-calibrate-optics-set") {
    applyParentOptics(ev.data);
  }
});

function notifyParentPointsChanged() {
  if (!window.parent || window.parent === window) {
    return;
  }
  if (!document.body.classList.contains("ss-embed")) {
    return;
  }
  window.parent.postMessage(
    { type: "ss-calibrate-points-changed" },
    window.location.origin,
  );
}

function waitForCanvasLayout(canvas, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const started = performance.now();
    const tick = () => {
      if (canvas && canvas.clientWidth > 2 && canvas.clientHeight > 2) {
        resolve();
        return;
      }
      if (performance.now() - started > timeoutMs) {
        resolve();
        return;
      }
      requestAnimationFrame(tick);
    };
    tick();
  });
}

function applyParentOptics(data) {
  const inn = data.intrinsics || {};
  const dist = data.distortion || {};
  const fix = data.fixIntrinsics || {};

  const setVal = (name, value) => {
    if (value === undefined || value === null) {
      return;
    }
    const el = document.getElementById(`id_${name}`);
    if (el) {
      el.value = value;
    }
  };

  setVal("intrinsics_fx", inn.fx);
  setVal("intrinsics_fy", inn.fy);
  setVal("intrinsics_cx", inn.cx);
  setVal("intrinsics_cy", inn.cy);
  setVal("distortion_k1", dist.k1);
  setVal("distortion_k2", dist.k2);
  setVal("distortion_p1", dist.p1);
  setVal("distortion_p2", dist.p2);
  setVal("distortion_k3", dist.k3);

  ["fx", "fy"].forEach((key) => {
    const locked = Boolean(fix[key]);
    const box = document.getElementById(`enabled_intrinsics_${key}`);
    const input = document.getElementById(`id_intrinsics_${key}`);
    if (box) {
      box.checked = locked;
    }
    if (input) {
      input.disabled = locked;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (!document.body.classList.contains("ss-embed")) {
    return;
  }
  const root = document.getElementById("calibration_form");
  if (!root) {
    return;
  }

  // Match CamCalibrateForm defaults: lock checkboxes constrain fx/fy.
  ["fx", "fy"].forEach((key) => {
    const box = document.getElementById(`enabled_intrinsics_${key}`);
    const input = document.getElementById(`id_intrinsics_${key}`);
    if (box && input) {
      input.disabled = box.checked;
      box.addEventListener("change", () => {
        input.disabled = box.checked;
        notifyParentCalibrationFields();
      });
    }
  });

  root.addEventListener("input", (ev) => {
    const t = ev.target;
    if (
      t &&
      t.name &&
      (t.name.startsWith("intrinsics_") || t.name.startsWith("distortion_"))
    ) {
      notifyParentCalibrationFields();
    }
  });
});

export class ConvergedCameraCalibration {
  constructor() {
    this.camCanvas = null;
    this.viewport = null;
    this.client = null;
    this.isUpdatedInVAService = false;
    this.projectionEnabled = false;
    this.isResolutionUpdated = false;

    // Used for storing undistorted image for projection
    this.projectionImage = new Image();
    this.projectionCanvas = $("<canvas></canvas>")[0];
    this.projectionCtx = this.projectionCanvas.getContext("2d", {
      willReadFrequently: true,
    });

    this.textureLoader = new THREE.TextureLoader();
    this.expandedPane = null;
    this.#initializePaneExpandControls();
  }

  /**
   * Sets the MQTT client to re-use the client defined at the upper level. Adds an event
   * listener to the client to check if the intrinsics have been updated in VA.
   * @param {mqtt.Client} client - The MQTT client to use for communication
   * @param {string} cameraTopic - The topic for the camera image
   */
  setMqttClient(client, cameraTopic) {
    this.client = client;

    this.client.on("message", (topic, message) => {
      // Uses the topic for the camera image, as it is the only topic that sends intrinsics
      // when there are no detections in the scene
      if (topic === cameraTopic) {
        let msg = JSON.parse(message);
        const intrinsics = this.getIntrinsics();

        this.isUpdatedInVAService = compareIntrinsics(
          intrinsics["intrinsics"],
          msg.intrinsics.flat(),
          intrinsics["distortion"],
          msg.distortion,
        );
      }
    });
  }

  initializeCamCanvas(canvasElement, imageSrc) {
    this.camCanvas = new CamCanvas(canvasElement, imageSrc);
    // FIXME: Find a better way to do these event listeners which require interacting with both
    // the camCanvas and viewport
    this.camCanvas.canvas.addEventListener("mouseup", () => {
      if (this.camCanvas.consumePointEdit()) {
        this.calculateCalibrationIntrinsics();
        notifyParentPointsChanged();
      }
    });
    this.camCanvas.canvas.addEventListener("dblclick", () => {
      if (this.camCanvas.consumePointEdit()) {
        this.calculateCalibrationIntrinsics();
        notifyParentPointsChanged();
      }
    });
    this.camCanvas.canvas.addEventListener("contextmenu", () => {
      if (this.camCanvas.consumePointEdit()) {
        this.calculateCalibrationIntrinsics();
        notifyParentPointsChanged();
      }
    });
    this.camCanvas.canvas.addEventListener("mousemove", (event) => {
      if (this.camCanvas.isDragging) {
        this.projectionEnabled = false;
      }
    });
  }

  initializeViewport(canvas, scale, sceneID, authToken) {
    const gltfLoader = new GLTFLoader();
    const renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: true,
    });
    const viewport = new Viewport(
      canvas,
      scale,
      sceneID,
      authToken,
      gltfLoader,
      renderer,
    );
    this.viewport = viewport;

    this.viewportReady = viewport
      .loadMap()
      .then(() => viewport.initializeScene())
      .then(() => waitForCanvasLayout(viewport.renderer.domElement))
      .then(() => {
        function animate() {
          if (resizeRendererToDisplaySize(viewport.renderer)) {
            const canvas = viewport.renderer.domElement;
            viewport.perspectiveCamera.aspect =
              canvas.clientWidth / canvas.clientHeight;
            viewport.perspectiveCamera.updateProjectionMatrix();
            viewport.updateCalibrationPointScale();
          }

          viewport.orbitControls.update();
          renderer.render(viewport, viewport.perspectiveCamera);
          requestAnimationFrame(animate);
        }

        animate();
        viewport.initializeEventListeners();

        viewport.renderer.domElement.addEventListener("mouseup", () => {
          if (viewport.consumePointEdit()) {
            this.calculateCalibrationIntrinsics();
            notifyParentPointsChanged();
          }
        });
        viewport.renderer.domElement.addEventListener("dblclick", () => {
          if (viewport.consumePointEdit()) {
            this.calculateCalibrationIntrinsics();
            notifyParentPointsChanged();
          }
        });
        viewport.renderer.domElement.addEventListener("contextmenu", () => {
          if (viewport.consumePointEdit()) {
            this.calculateCalibrationIntrinsics();
            notifyParentPointsChanged();
          }
        });
        viewport.renderer.domElement.addEventListener("mousemove", () => {
          if (viewport.isDragging) {
            this.projectionEnabled = false;
          }
        });
      });
  }

  #calculateDeterminant(points) {
    const [p1, p2, p3, p4] = points;

    const v1 = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]];
    const v2 = [p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]];
    const v3 = [p4[0] - p1[0], p4[1] - p1[1], p4[2] - p1[2]];

    return (
      v1[0] * (v2[1] * v3[2] - v2[2] * v3[1]) -
      v1[1] * (v2[0] * v3[2] - v2[2] * v3[0]) +
      v1[2] * (v2[0] * v3[1] - v2[1] * v3[0])
    );
  }

  arePointsCoplanar(points) {
    // Only need to check for lengths of 4 or 5
    if (points.length === 5) {
      for (let i = 0; i < points.length; i++) {
        const subset = points.filter((_, index) => index !== i);
        if (
          Math.abs(
            this.#calculateDeterminant(subset) > MAX_COPLANAR_DETERMINANT,
          )
        ) {
          return false;
        }
      }
    } else if (points.length === 4) {
      return (
        Math.abs(this.#calculateDeterminant(points)) < MAX_COPLANAR_DETERMINANT
      );
    }
    return true;
  }

  isValidCalibration(camPoints, mapPoints) {
    // Only calibrate when dragging is complete
    if (this.camCanvas.isDragging || this.viewport.isDragging) {
      return false;
    }
    const camPointNames = Object.keys(camPoints);
    const mapPointNames = Object.keys(mapPoints);
    const matchingNames = camPointNames.filter((name) =>
      mapPointNames.includes(name),
    );

    if (
      matchingNames.length >= 4 &&
      camPointNames.length === mapPointNames.length
    ) {
      return true;
    }
    return false;
  }

  getIntrinsics() {
    return {
      intrinsics: {
        fx: parseFloat($("#id_intrinsics_fx").val()),
        fy: parseFloat($("#id_intrinsics_fy").val()),
        cx: parseFloat($("#id_intrinsics_cx").val()),
        cy: parseFloat($("#id_intrinsics_cy").val()),
      },
      distortion: {
        k1: parseFloat($("#id_distortion_k1").val()),
        k2: parseFloat($("#id_distortion_k2").val()),
        p1: parseFloat($("#id_distortion_p1").val()),
        p2: parseFloat($("#id_distortion_p2").val()),
        k3: parseFloat($("#id_distortion_k3").val()),
      },
    };
  }

  calculateCalibrationIntrinsics() {
    const camPoints = this.camCanvas.getCalibrationPoints();
    const mapPoints = this.viewport.getCalibrationPoints(true);
    if (
      this.isValidCalibration(camPoints, mapPoints) &&
      Object.keys(camPoints).length >= 6
    ) {
      const intrinsicCheckboxes = $('input[type="checkbox"][name^="enabled_"]');
      const fixIntrinsics = {};
      intrinsicCheckboxes.each(function () {
        const name = this.name.split("_")[2];
        fixIntrinsics[name] = this.checked;
      });

      // Collect intrinsic and distortion data
      const intrinsicData = [];
      const distortionData = [];
      let fx, fy, cx, cy;

      $('input[name^="intrinsics_"]').each(function () {
        if (this.name === "intrinsics_fx") fx = parseFloat(this.value);
        if (this.name === "intrinsics_fy") fy = parseFloat(this.value);
        if (this.name === "intrinsics_cx") cx = parseFloat(this.value);
        if (this.name === "intrinsics_cy") cy = parseFloat(this.value);
      });

      // Format the intrinsic data into a matrix
      intrinsicData.push([fx, 0, cx]);
      intrinsicData.push([0, fy, cy]);
      intrinsicData.push([0, 0, 1]);

      $('input[name^="distortion_"]').each(function () {
        distortionData.push(parseFloat(this.value));
      });

      const data = {
        camPoints: Object.values(camPoints),
        mapPoints: Object.values(mapPoints),
        fixIntrinsics: fixIntrinsics,
        intrinsics: intrinsicData,
        distortion: distortionData,
        imageSize: this.camCanvas.getImageSize(),
      };

      $.ajax({
        url: `${REST_URL}/calculateintrinsics`,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Token ${$("#auth-token").val()}`,
        },
        data: JSON.stringify(data),
        contentType: "application/json",
        success: function (response) {
          // Fill out the corresponding intrinsic and distortion fields if they are not disabled
          const intrinsicMtx = response["mtx"].flat();
          $('input[name^="intrinsics_"]').each(function () {
            if (!$(this).prop("disabled")) {
              if (this.name === "intrinsics_fx") this.value = intrinsicMtx[FX];
              if (this.name === "intrinsics_fy") this.value = intrinsicMtx[FY];
              if (this.name === "intrinsics_cx") this.value = intrinsicMtx[CX];
              if (this.name === "intrinsics_cy") this.value = intrinsicMtx[CY];
            }
          });
          $('input[name^="distortion_"]').each(function () {
            if (!$(this).prop("disabled")) {
              if (this.name === "distortion_k1")
                this.value = response["dist"][K1];
              if (this.name === "distortion_k2")
                this.value = response["dist"][K2];
              if (this.name === "distortion_p1")
                this.value = response["dist"][P1];
              if (this.name === "distortion_p2")
                this.value = response["dist"][P2];
              if (this.name === "distortion_k3")
                this.value = response["dist"][K3];
            }
          });
          notifyParentCalibrationFields();
        },
        error: function (error) {
          // If invalid values are passed, print the error text
          console.log(error.responseText);
        },
      });
    }
  }

  #placeSceneCalibrationPoint(x, y, z) {
    let px = x;
    let py = y;
    let pz = z;
    const floorW = this.viewport.floorWidth || 0;
    const floorH = this.viewport.floorHeight || 0;
    const scale = this.viewport.sceneScale || 100;
    // Stored map points are meters. Legacy / mistaken pixel values sit far
    // outside the floor and must be converted.
    if (
      floorW > 0 &&
      floorH > 0 &&
      (Math.abs(px) > floorW * 1.5 || Math.abs(py) > floorH * 1.5)
    ) {
      px /= scale;
      py /= scale;
      pz /= scale;
    }
    this.viewport.addCalibrationPoint(px, py, pz);
  }

  addInitialCalibrationPoints(points, transformType) {
    const kind = String(transformType || "").trim();
    if (kind && kind !== "3d-2d point correspondence") {
      return;
    }
    const values = points
      .map((value) => parseFloat(value))
      .filter((value) => Number.isFinite(value));
    if (values.length % 5 === 0) {
      const splitPoint = (values.length / 5) * 2;
      for (let i = 0; i < splitPoint; i += 2) {
        this.camCanvas.addCalibrationPoint(values[i], values[i + 1]);
      }
      for (let i = splitPoint; i < values.length; i += 3) {
        this.#placeSceneCalibrationPoint(
          values[i],
          values[i + 1],
          values[i + 2],
        );
      }
    } else if (values.length % 2 === 0) {
      const splitPoint = values.length / 2;
      for (let i = 0; i < splitPoint; i += 2) {
        this.camCanvas.addCalibrationPoint(values[i], values[i + 1]);
      }
      for (let i = splitPoint; i < values.length; i += 2) {
        this.#placeSceneCalibrationPoint(values[i], values[i + 1], 0);
      }
    }
    if (this.camCanvas) {
      this.camCanvas.calibrationUpdated = false;
      this.camCanvas.pointEdited = false;
      this.camCanvas.drawImage();
    }
    if (this.viewport) {
      this.viewport.calibrationUpdated = false;
      this.viewport.pointEdited = false;
      this.viewport.updateCalibrationPointScale();
      this.viewport.frameCalibrationPoints();
    }
  }

  addAutoCalibrationPoints(msg) {
    const number_of_apriltags = msg.calibration_points_2d.length;

    for (let i = 1; i <= number_of_apriltags; i++) {
      const cam_coord = msg.calibration_points_2d[i - 1];
      const map_coord = msg.calibration_points_3d[i - 1];

      this.camCanvas.addCalibrationPoint(cam_coord[0], cam_coord[1]);
      this.viewport.addCalibrationPoint(
        map_coord[0],
        map_coord[1],
        map_coord[2],
      );
    }
    notifyParentPointsChanged();
  }

  clearCalibrationPoints() {
    this.camCanvas.clearCalibrationPoints();
    this.viewport.clearCalibrationPoints();
    this.projectionEnabled = false;
    notifyParentPointsChanged();
  }

  setupResetPointsButton() {
    $("#reset_points").on("click", () => {
      this.clearCalibrationPoints();
    });
  }

  setupResetViewButton() {
    $("#reset_view").on("click", () => {
      this.camCanvas.resetCameraView();
      this.viewport.resetCameraView();
      this.viewport.updateCalibrationPointScale();
    });
  }

  setupOpacitySlider() {
    const previousOpacity = localStorage.getItem("opacity");
    if (previousOpacity !== null) {
      $("#overlay_opacity").val(previousOpacity);
      this.viewport.setProjectionOpacity(previousOpacity / 100);
    } else {
      $("#overlay_opacity").val(INITIAL_PROJECTION_OPACITY);
      this.viewport.setProjectionOpacity(INITIAL_PROJECTION_OPACITY / 100);
    }

    // Update perspective overlay transparency when slider is moved
    $("#overlay_opacity").on("input", (event) => {
      const opacityValue = $(event.currentTarget).val();
      this.viewport.setProjectionOpacity(opacityValue / 100);
      localStorage.setItem("opacity", opacityValue);
    });
  }

  /**
   * Collect current point-correspondence pose for React REST save (no form POST).
   * @returns {{ transform_type: string, transforms: number[] } | null}
   */
  collectPose() {
    if (!this.camCanvas || !this.viewport) {
      return null;
    }
    const camPoints = this.camCanvas.getCalibrationPoints();
    const scenePoints = this.viewport.getCalibrationPoints();
    const camPointCount = Object.keys(camPoints).length;
    const scenePointCount = Object.keys(scenePoints).length;
    if (camPointCount === 0 && scenePointCount === 0) {
      return { transform_type: null, transforms: null, empty: true };
    }
    if (!this.isValidCalibration(camPoints, scenePoints)) {
      return {
        transform_type: null,
        transforms: null,
        empty: false,
        error:
          "Saving the calibration requires an equal number of calibration points in each view (minimum 4).",
        camPointCount,
        scenePointCount,
      };
    }
    const transforms = [
      ...Object.values(camPoints).flatMap((point) => [point[0], point[1]]),
      ...Object.values(scenePoints).flatMap((point) => [
        point[0],
        point[1],
        point[2],
      ]),
    ];
    return {
      transform_type: "3d-2d point correspondence",
      transforms,
      empty: false,
    };
  }

  setupSaveCameraButton() {
    $("#calibration_form").on("submit", (event) => {
      event.preventDefault();
      if (this.isResolutionUpdated) {
        document.getElementById("id_intrinsics_cx").disabled = false;
        document.getElementById("id_intrinsics_cy").disabled = false;
      }

      const camPoints = this.camCanvas.getCalibrationPoints();
      const scenePoints = this.viewport.getCalibrationPoints();
      const camPointCount = Object.keys(camPoints).length;
      const scenePointCount = Object.keys(scenePoints).length;
      const noPointsTouched = camPointCount === 0 && scenePointCount === 0;

      // Nothing calibration-related was touched (e.g. only editing name/id) —
      // let the rest of the form flow through untouched.
      if (noPointsTouched) {
        $("#calibration_form")[0].submit();
        return;
      }

      if (this.isValidCalibration(camPoints, scenePoints)) {
        const camPointsStr = Object.values(camPoints)
          .map((point) => `${point[0]},${point[1]}`)
          .join(",");
        const scenePointsStr = Object.values(scenePoints)
          .map((point) => `${point[0]},${point[1]},${point[2]}`)
          .join(",");
        $("#id_transforms").val(`${camPointsStr},${scenePointsStr}`);
        $("#id_transform_type").val("3d-2d point correspondence");

        if (this.client) {
          const intrinsicData = {
            updatecamera: this.getIntrinsics(),
          };
          const topic = APP_NAME + CMD_CAMERA + $("#sensor_id").val();
          this.client.publish(topic, JSON.stringify(intrinsicData), { qos: 1 });
          // Wait for data to be updated in VA
          // FIXME: Unify with code in scenecamera.js
          waitUntil(
            () => this.isUpdatedInVAService,
            100,
            MAX_INTRINSICS_UPDATE_WAIT_TIME,
          )
            .then(() => {
              // If intrinsics are unlocked, inform the user to remove the override flag
              if (
                $("#id_intrinsics_fx").prop("disabled") === false &&
                $("#id_intrinsics_fy").prop("disabled") === false
              ) {
                alert(
                  'Camera updated. Ensure "--override-saved-intrinsics" is not set for ' +
                    "this camera in docker-compose.yml to have these changes persist.",
                );
              } else {
                alert("Camera updated");
              }
              $("#calibration_form")[0].submit();
            })
            .catch((error) => {
              alert(
                "Failed to update camera intrinsics in Video Analytics Service. Please try again.\n\n" +
                  "If you keep getting this error, please check the documentation for " +
                  "known issues.",
              );
            });
        } else {
          $("#calibration_form")[0].submit();
        }
      } else {
        alert(
          "Saving the calibration requires an equal number of calibration points in each " +
            "view (minimum 4).\n\n" +
            `There are currently ${camPointCount} points in the camera ` +
            `view and ${scenePointCount} points in the scene view.`,
        );
      }
    });
  }

  getCameraPositionAndRotation(cameraMatrix, distCoeffs) {
    const camPoints = this.camCanvas.getCalibrationPoints();
    const objectPoints = this.viewport.getCalibrationPoints();
    if (
      this.isValidCalibration(camPoints, objectPoints) &&
      (this.camCanvas.calibrationUpdated ||
        this.viewport.calibrationUpdated ||
        this.isResolutionUpdated)
    ) {
      let rvec = new cv.Mat();
      let tvec = new cv.Mat();
      let R = new cv.Mat();

      // Convert imagePoints and objectPoints to cv.Mat
      const camPointsArray = Object.values(camPoints);
      const objectPointsArray = Object.values(objectPoints);
      const imagePointsMat = cv.matFromArray(
        camPointsArray.length,
        2,
        cv.CV_64F,
        camPointsArray.flat(),
      );
      const objectPointsMat = cv.matFromArray(
        objectPointsArray.length,
        3,
        cv.CV_64F,
        objectPointsArray.flat(),
      );
      let cameraMatrixMat = cv.matFromArray(
        3,
        3,
        cv.CV_64F,
        cameraMatrix.flat(),
      );
      let distCoeffsMat = cv.matFromArray(1, 5, cv.CV_64F, distCoeffs.flat());

      let computationMethod = cv.SOLVEPNP_ITERATIVE;
      // If we do not have coplanar points and fewer than 6 points, use SQPNP
      if (this.arePointsCoplanar(objectPointsArray) === false) {
        computationMethod = cv.SOLVEPNP_SQPNP;
      }
      // Prepare other necessary parameters
      cv.solvePnP(
        objectPointsMat,
        imagePointsMat,
        cameraMatrixMat,
        distCoeffsMat,
        rvec,
        tvec,
        false,
        computationMethod,
      );
      cv.Rodrigues(rvec, R);
      let T = new THREE.Matrix4();
      //OpenCV to OpenGL coordinate system alignment requires negating rows 2 and 3 in transform matrix
      //https://stackoverflow.com/questions/44375149/opencv-to-opengl-coordinate-system-transform
      T.set(
        R.data64F[0],
        R.data64F[1],
        R.data64F[2],
        tvec.data64F[0],
        -R.data64F[3],
        -R.data64F[4],
        -R.data64F[5],
        -tvec.data64F[1],
        -R.data64F[6],
        -R.data64F[7],
        -R.data64F[8],
        -tvec.data64F[2],
        0,
        0,
        0,
        1,
      );
      T.invert(); //Format of T is column-major. Hence, T.transpose lines up with transform.py values.
      this.viewport.setCameraPose(T);
      this.projectionEnabled = true;
      this.camCanvas.calibrationUpdated = false;
      this.viewport.calibrationUpdated = false;
    }
  }

  undistortAndProjectImage(image, cameraMatrix, distCoeffs) {
    this.projectionImage.src = image;
    this.projectionImage.onload = () => {
      this.projectionCanvas.width = this.projectionImage.width;
      this.projectionCanvas.height = this.projectionImage.height;
      this.projectionCtx.drawImage(this.projectionImage, 0, 0);
      const distortedImage = cv.imread(this.projectionCanvas);

      const h = distortedImage.rows;
      const w = distortedImage.cols;

      const map_x = new cv.Mat();
      const map_y = new cv.Mat();
      const cameraMatrixMat = cv.matFromArray(
        3,
        3,
        cv.CV_64F,
        cameraMatrix.flat(),
      );
      const distCoeffsMat = cv.matFromArray(1, 5, cv.CV_64F, distCoeffs.flat());
      // 3x3 identity matrix
      const identityMatrix = cv.matFromArray(
        3,
        3,
        cv.CV_64F,
        [1, 0, 0, 0, 1, 0, 0, 0, 1],
      );
      cv.initUndistortRectifyMap(
        cameraMatrixMat,
        distCoeffsMat,
        identityMatrix,
        cameraMatrixMat,
        new cv.Size(w, h),
        5,
        map_x,
        map_y,
      );
      const undistortedImage = new cv.Mat();
      cv.remap(distortedImage, undistortedImage, map_x, map_y, cv.INTER_LINEAR);

      // Put undistorted image on canvas to use with projection later
      const imageData = new ImageData(
        new Uint8ClampedArray(undistortedImage.data),
        undistortedImage.cols,
        undistortedImage.rows,
      );
      this.projectionCtx.putImageData(imageData, 0, 0);

      this.projectImage(
        this.projectionCanvas.toDataURL("image/jpeg"),
        cameraMatrix,
      );

      distortedImage.delete();
      undistortedImage.delete();
      map_x.delete();
      map_y.delete();
      cameraMatrixMat.delete();
      distCoeffsMat.delete();
      identityMatrix.delete();
    };
  }

  projectImage(image, cameraMatrix) {
    if (this.projectionEnabled === false) {
      this.viewport.setProjectionVisibility(false);
      return;
    }
    this.viewport.projectImage(image, cameraMatrix);
  }

  updateCameraOpticalCenter(resolution, cameraMatrix) {
    const [width, height] = resolution;
    const EPSILON = 1e-6;
    if (
      Math.abs(parseFloat($("#id_intrinsics_cx").val()) - width / 2.0) > EPSILON
    ) {
      $("#id_intrinsics_cx").val(width / 2.0);
      cameraMatrix[0][2] = width / 2.0;
      this.isResolutionUpdated = true;
    }
    if (
      Math.abs(parseFloat($("#id_intrinsics_cy").val()) - height / 2.0) >
      EPSILON
    ) {
      $("#id_intrinsics_cy").val(height / 2.0);
      cameraMatrix[1][2] = height / 2.0;
      this.isResolutionUpdated = true;
    }
  }

  updateCalibrationViews(image, cameraMatrix, distCoeffs) {
    this.camCanvas.updateImageSrc(image);
    this.updateCameraOpticalCenter(this.camCanvas.getImageSize(), cameraMatrix);
    this.getCameraPositionAndRotation(cameraMatrix, distCoeffs);
    if (distCoeffs.some((coeff) => coeff !== 0)) {
      this.undistortAndProjectImage(image, cameraMatrix, distCoeffs);
    } else {
      this.projectImage(image, cameraMatrix);
    }
  }

  #initializePaneExpandControls() {
    const backdrop = document.getElementById("cal-pane-backdrop");
    const buttons = document.querySelectorAll("[data-cal-expand]");
    if (!backdrop || !buttons.length) {
      return;
    }

    buttons.forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        const pane = button.closest(".cal-pane");
        if (!pane) {
          return;
        }
        if (pane.classList.contains("is-expanded")) {
          this.collapseCalibrationPane();
        } else {
          this.expandCalibrationPane(pane);
        }
      });
    });

    backdrop.addEventListener("click", () => {
      this.collapseCalibrationPane();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && this.expandedPane) {
        this.collapseCalibrationPane();
      }
    });
  }

  #setExpandButtonState(pane, expanded) {
    const button = pane.querySelector("[data-cal-expand]");
    if (!button) {
      return;
    }
    const icon = button.querySelector("i");
    const label = button.querySelector(".sr-only");
    const title = pane.getAttribute("aria-label") || "view";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    button.title = expanded ? `Collapse ${title}` : `Expand ${title}`;
    if (icon) {
      icon.className = expanded ? "bi bi-fullscreen-exit" : "bi bi-fullscreen";
    }
    if (label) {
      label.textContent = expanded
        ? `Collapse ${title}`
        : `Expand ${title}`;
    }
  }

  expandCalibrationPane(pane) {
    if (this.expandedPane && this.expandedPane !== pane) {
      this.collapseCalibrationPane();
    }

    const backdrop = document.getElementById("cal-pane-backdrop");
    pane.classList.add("is-expanded");
    this.expandedPane = pane;
    this.#setExpandButtonState(pane, true);
    if (backdrop) {
      backdrop.hidden = false;
    }
    document.body.classList.add("cal-pane-expanded");

    // Allow layout to settle before canvas resize observers run
    requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
    });
  }

  collapseCalibrationPane() {
    if (!this.expandedPane) {
      return;
    }

    const pane = this.expandedPane;
    const backdrop = document.getElementById("cal-pane-backdrop");
    pane.classList.remove("is-expanded");
    this.#setExpandButtonState(pane, false);
    this.expandedPane = null;
    if (backdrop) {
      backdrop.hidden = true;
    }
    document.body.classList.remove("cal-pane-expanded");

    requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
    });
  }
}
