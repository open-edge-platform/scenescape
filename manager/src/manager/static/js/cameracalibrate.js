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
  CALIBRATION_MIN_POINTS_FOR_FIT,
  CALIBRATION_OUTLIER_THRESHOLD_PX,
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
import {
  PTZ_AWAY_MESSAGE,
  PTZFrameGate,
  PTZPoseExpiry,
  createPTZPointMapper,
  expiredPTZPoseContext,
  isPTZAwayFromHomePose,
  isPTZMoving,
  isPTZPositionUnknown,
  ptzMatricesClose,
  ptzPoseToCameraMatrix,
  sceneFromCameraToCameraMatrix,
} from "/static/js/ptzpose.js";

export class ConvergedCameraCalibration {
  constructor() {
    this.camCanvas = null;
    this.viewport = null;
    this.client = null;
    this.isUpdatedInVAService = false;
    this.projectionEnabled = false;
    // Retain resolution changes for Save even after the preview refit completes.
    this.isResolutionUpdated = false;
    this.resolutionNeedsRefit = false;
    this.calibrationRequestId = 0;
    this.calibrationFitState = "idle";
    this.rejectedPointIndices = [];
    // Live PTZ pose state; null until a PoseContext is received.
    this.ptzPoseValid = null;
    this.ptzMoving = false;
    // Positioning reported an invalid pose while not moving; the home pose is shown.
    this.ptzPositionUnknown = false;
    this.ptzLiveMatrix = null;
    this.ptzLivePoseMatrix = null;
    // Stored home pose matrix: undefined while loading, null when unavailable.
    this.ptzHomePoseMatrix = undefined;
    this.ptzHomeRequested = false;
    this.ptzPointMapperKey = null;
    this.ptzPendingPoints = null;
    // Frame admission and expiry for the live PTZ pose.
    this.ptzFrameGate = new PTZFrameGate();
    this.ptzPoseExpiry = new PTZPoseExpiry();
    // Calibration (home) pose last set by calibration fitting or the stored pose.
    this.calibrationPoseMatrix = null;

    // Used for storing undistorted image for projection
    this.projectionImage = new Image();
    this.projectionCanvas = $("<canvas></canvas>")[0];
    this.projectionCtx = this.projectionCanvas.getContext("2d", {
      willReadFrequently: true,
    });

    this.textureLoader = new THREE.TextureLoader();
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
    this.camCanvas = new CamCanvas(canvasElement, imageSrc, () =>
      this.flushSensorCalibrationPoints(),
    );
    // FIXME: Find a better way to do these event listeners which require interacting with both
    // the camCanvas and viewport
    this.camCanvas.canvas.addEventListener("mousedown", () => {
      // CamCanvas handles the hit-test first; clear markers once a point drag starts.
      if (this.camCanvas.isDragging) {
        this.clearCalibrationPointDiagnostics();
      }
    });
    this.camCanvas.canvas.addEventListener("mouseup", (event) => {
      // Right-button mouseup fires before contextmenu; wait for contextmenu
      // so point deletion is applied before recalculating.
      if (event.button === 2) {
        return;
      }
      this.calculateCalibrationIntrinsics();
    });
    this.camCanvas.canvas.addEventListener("dblclick", (event) => {
      this.calculateCalibrationIntrinsics();
    });
    this.camCanvas.canvas.addEventListener("contextmenu", (event) => {
      this.calculateCalibrationIntrinsics();
    });
    // CamCanvas ends drags on mouseleave; refit so Save is not stuck on stale.
    this.camCanvas.canvas.addEventListener("mouseleave", () => {
      if (this.calibrationFitState === "stale") {
        this.calculateCalibrationIntrinsics();
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

    viewport
      .loadMap()
      .then(() => {
        viewport.initializeScene();

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
      })
      .then(() => {
        viewport.initializeEventListeners();

        viewport.renderer.domElement.addEventListener("mousedown", () => {
          // Viewport handles the hit-test first; clear markers once a point drag starts.
          if (viewport.isDragging) {
            this.clearCalibrationPointDiagnostics();
          }
        });
        viewport.renderer.domElement.addEventListener("mouseup", (event) => {
          // Right-button mouseup fires before contextmenu; wait for contextmenu
          // so point deletion is applied before recalculating.
          if (event.button === 2) {
            return;
          }
          this.calculateCalibrationIntrinsics();
        });
        viewport.renderer.domElement.addEventListener("dblclick", (event) => {
          this.calculateCalibrationIntrinsics();
        });
        viewport.renderer.domElement.addEventListener(
          "contextmenu",
          (event) => {
            this.calculateCalibrationIntrinsics();
          },
        );
        viewport.renderer.domElement.addEventListener("mouseleave", (event) => {
          if (viewport.isDragging) {
            viewport.onMouseUp(event);
          }
          if (this.calibrationFitState === "stale") {
            this.calculateCalibrationIntrinsics();
          }
        });
        viewport.renderer.domElement.addEventListener("mousemove", (event) => {
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
          Math.abs(this.#calculateDeterminant(subset)) >
          MAX_COPLANAR_DETERMINANT
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
    if (
      camPointNames.length < CALIBRATION_MIN_POINTS_FOR_FIT ||
      camPointNames.length !== mapPointNames.length
    ) {
      return false;
    }
    // Equal counts are not enough: deleting differently named points in each
    // view can leave four shared names and one camera-only / map-only name.
    const mapNameSet = new Set(mapPointNames);
    return camPointNames.every((name) => mapNameSet.has(name));
  }

  calibrationPointNamesMatch(camPoints, mapPoints) {
    const camPointNames = Object.keys(camPoints);
    const mapPointNames = Object.keys(mapPoints);
    if (camPointNames.length !== mapPointNames.length) {
      return false;
    }
    const mapNameSet = new Set(mapPointNames);
    return camPointNames.every((name) => mapNameSet.has(name));
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
    if (!this.centerManualIntrinsics()) return;
    const requestId = ++this.calibrationRequestId;
    const camPoints = this.getSensorCalibrationPoints();
    const mapPoints = this.viewport.getCalibrationPoints(true);
    this.calibrationFitState = "stale";
    if (
      this.isValidCalibration(camPoints, mapPoints) &&
      Object.keys(camPoints).length >= CALIBRATION_MIN_POINTS_FOR_FIT
    ) {
      this.calibrationFitState = "pending";
      const pointNames = Object.keys(camPoints);
      this.rejectedPointIndices = [];
      this.setCalibrationFitStatus("Checking calibration point fit...", [], []);
      const intrinsicCheckboxes = $('input[type="checkbox"][name^="enabled_"]');
      const fixIntrinsics = {};
      intrinsicCheckboxes.each(function () {
        const name = this.name.split("_")[2];
        fixIntrinsics[name] = this.checked;
      });
      fixIntrinsics.cx = fixIntrinsics.cy = true;

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

      const sceneScale = parseFloat($("#scale").val());
      const data = {
        camPoints: pointNames.map((name) => camPoints[name]),
        mapPoints: pointNames.map((name) => mapPoints[name]),
        fixIntrinsics: fixIntrinsics,
        intrinsics: intrinsicData,
        distortion: distortionData,
        imageSize: this.getSensorResolution(),
      };
      // Scene map resolution scales the RANSAC reprojection threshold.
      if (Number.isFinite(sceneScale) && sceneScale > 0) {
        data.pixelsPerMeter = sceneScale;
      }

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
          if (requestId !== this.calibrationRequestId) {
            return;
          }
          // Fill out the corresponding intrinsic and distortion fields if they are not disabled
          const intrinsicMtx = response["mtx"].flat();
          const distCoeffs = response["dist"].flat();
          $('input[name^="intrinsics_"]').each(function () {
            if (!$(this).prop("disabled")) {
              if (this.name === "intrinsics_fx") this.value = intrinsicMtx[FX];
              if (this.name === "intrinsics_fy") this.value = intrinsicMtx[FY];
            }
          });
          $('input[name^="distortion_"]').each(function () {
            if (!$(this).prop("disabled")) {
              if (this.name === "distortion_k1") this.value = distCoeffs[K1];
              if (this.name === "distortion_k2") this.value = distCoeffs[K2];
              if (this.name === "distortion_p1") this.value = distCoeffs[P1];
              if (this.name === "distortion_p2") this.value = distCoeffs[P2];
              if (this.name === "distortion_k3") this.value = distCoeffs[K3];
            }
          });
          this.rejectedPointIndices = response.rejectionApplied
            ? response.rejectedIndices || []
            : [];
          // Use the API-fitted pose so the preview matches the server model
          // (browser-side solvePnP can diverge, especially on planar sets).
          if (!this.applyFittedCalibrationPose(response)) {
            this.calibrationFitState = "failed";
            this.setCalibrationFitStatus(
              "Could not apply the fitted camera pose preview. " +
                "Adjust the point pairs and try again.",
              [],
              [],
            );
            return;
          }
          this.showCalibrationFitStatus(response, pointNames);
          this.calibrationFitState = "ready";
        }.bind(this),
        error: function (error) {
          if (requestId !== this.calibrationRequestId) {
            return;
          }
          this.calibrationFitState = "failed";
          // If invalid values are passed, print the error text
          console.log(error.responseText);
          this.rejectedPointIndices = [];
          this.setCalibrationFitStatus(
            "Could not evaluate the calibration fit. Check the point pairs and try again.",
            [],
            [],
          );
        }.bind(this),
      });
    } else {
      if (
        this.isValidCalibration(camPoints, mapPoints) &&
        Object.keys(camPoints).length < CALIBRATION_MIN_POINTS_FOR_FIT
      ) {
        this.calibrationFitState = "ready";
      }
      this.rejectedPointIndices = [];
      if (
        this.isValidCalibration(camPoints, mapPoints) &&
        Object.keys(camPoints).length >= CALIBRATION_MIN_POINTS_FOR_FIT
      ) {
        this.updateCalibrationPoseFromFit();
      }
      const diagnostics = document.getElementById("calibration-diagnostics");
      if (diagnostics && !diagnostics.hidden) {
        const cameraCount = Object.keys(camPoints).length;
        const mapCount = Object.keys(mapPoints).length;
        const message = !this.calibrationPointNamesMatch(camPoints, mapPoints)
          ? `Place matching point pairs with the same names in both views (${cameraCount} camera, ${mapCount} map).`
          : `Add at least ${CALIBRATION_MIN_POINTS_FOR_FIT} matching point pairs to evaluate the calibration fit (${cameraCount} currently placed).`;
        this.setCalibrationFitStatus(message, [], []);
      }
    }
  }

  applyFittedCalibrationPose(response) {
    const matrix = response && response.poseMatrix;
    if (!Array.isArray(matrix) || matrix.length !== 4) {
      return false;
    }
    const flat = matrix.flat().map(Number);
    if (flat.length !== 16 || !flat.every(Number.isFinite)) {
      return false;
    }
    // The fit request uses scaled map coordinates; the viewport uses metres.
    const coordinateScale =
      Number(this.viewport.sceneScale) * this.viewport.scaleFactor;
    if (!Number.isFinite(coordinateScale) || coordinateScale <= 0) {
      return false;
    }
    const pose = new THREE.Matrix4();
    pose.set(
      flat[0],
      flat[1],
      flat[2],
      flat[3] / coordinateScale,
      flat[4],
      flat[5],
      flat[6],
      flat[7] / coordinateScale,
      flat[8],
      flat[9],
      flat[10],
      flat[11] / coordinateScale,
      flat[12],
      flat[13],
      flat[14],
      flat[15],
    );
    this.viewport.setCameraPose(pose);
    this.rememberCalibrationPose();
    this.projectionEnabled = true;
    this.camCanvas.calibrationUpdated = false;
    this.viewport.calibrationUpdated = false;
    this.resolutionNeedsRefit = false;
    return true;
  }

  updateCalibrationPoseFromFit() {
    this.camCanvas.calibrationUpdated = true;
    this.viewport.calibrationUpdated = true;
    const cameraMatrix = [
      [
        parseFloat($("#id_intrinsics_fx").val()),
        0,
        parseFloat($("#id_intrinsics_cx").val()),
      ],
      [
        0,
        parseFloat($("#id_intrinsics_fy").val()),
        parseFloat($("#id_intrinsics_cy").val()),
      ],
      [0, 0, 1],
    ];
    const distCoeffs = [
      parseFloat($("#id_distortion_k1").val()),
      parseFloat($("#id_distortion_k2").val()),
      parseFloat($("#id_distortion_p1").val()),
      parseFloat($("#id_distortion_p2").val()),
      parseFloat($("#id_distortion_k3").val()),
    ];
    return this.getCameraPositionAndRotation(cameraMatrix, distCoeffs);
  }

  setCalibrationFitStatus(
    message,
    rejectedNames,
    highErrorNames,
    geometryWarnings = [],
  ) {
    const diagnostics = document.getElementById("calibration-diagnostics");
    const summary = document.getElementById("calibration-fit-summary");
    const guidance = document.getElementById("calibration-geometry-guidance");
    const warningList = document.getElementById(
      "calibration-geometry-warnings",
    );
    const details = document.getElementById("calibration-fit-details");
    const errors = document.getElementById("calibration-point-errors");
    if (!diagnostics || !summary) {
      return;
    }

    diagnostics.hidden = false;
    summary.textContent = message;
    if (guidance && warningList) {
      warningList.replaceChildren();
      if (geometryWarnings.length) {
        geometryWarnings.forEach((warning) => {
          const item = document.createElement("li");
          item.textContent = warning;
          warningList.appendChild(item);
        });
        guidance.hidden = false;
      } else {
        guidance.hidden = true;
      }
    }
    if (details) {
      details.hidden = true;
      details.open = false;
    }
    if (errors) {
      errors.replaceChildren();
    }
    this.camCanvas.setCalibrationPointDiagnostics(
      rejectedNames,
      highErrorNames,
    );
    this.viewport.setCalibrationPointDiagnostics(rejectedNames, highErrorNames);
  }

  showCalibrationFitStatus(response, pointNames) {
    const total = pointNames.length;
    const rejectedIndices = response.rejectedIndices || [];
    const rejectedIndexSet = new Set(rejectedIndices);
    const rejectedNames = rejectedIndices
      .map((index) => pointNames[index])
      .filter(Boolean);
    const threshold = Number(response.outlierThresholdPx);
    const safeThreshold = Number.isFinite(threshold)
      ? threshold
      : CALIBRATION_OUTLIER_THRESHOLD_PX;
    const errors = response.perPointErrors || [];
    const highErrorIndices = errors
      .map((error, index) =>
        error > safeThreshold && !rejectedIndexSet.has(index) ? index : -1,
      )
      .filter((index) => index >= 0);
    const highErrorNames = highErrorIndices
      .map((index) => pointNames[index])
      .filter(Boolean);
    const rms = Number(response.rmsError);
    const geometryWarnings = response.geometryWarnings || [];
    let message;

    if (response.rejectionApplied) {
      message =
        `${response.fitPointCount} of ${total} point pairs used in fit; ` +
        `${rejectedNames.length} rejected by RANSAC (${safeThreshold.toFixed(1)} px threshold).`;
    } else if (response.rejectionRequested) {
      message =
        response.ransacInlierCount === null
          ? `RANSAC could not estimate a usable inlier set; all ${response.fitPointCount} point pairs were used in the fit.`
          : `RANSAC found only ${response.ransacInlierCount} usable point pairs; at least ${CALIBRATION_MIN_POINTS_FOR_FIT} are needed. All ${response.fitPointCount} pairs were used in the fit.`;
    } else {
      message = `Outlier rejection is off; all ${response.fitPointCount} point pairs were used in the fit.`;
    }
    if (Number.isFinite(rms)) {
      message += ` Fit RMS reprojection error: ${rms.toFixed(2)} px.`;
    }
    if (highErrorNames.length) {
      message += ` ${highErrorNames.length} pair(s) have final residuals above ${safeThreshold.toFixed(1)} px.`;
    }
    this.setCalibrationFitStatus(
      message,
      rejectedNames,
      highErrorNames,
      geometryWarnings,
    );

    const details = document.getElementById("calibration-fit-details");
    const list = document.getElementById("calibration-point-errors");
    if (!details || !list || !errors.length) {
      return;
    }
    details.hidden = false;
    errors.forEach((error, index) => {
      const item = document.createElement("li");
      const pointName = pointNames[index] || `point ${index + 1}`;
      let state = "included";
      if (rejectedIndexSet.has(index)) {
        state = response.rejectionApplied
          ? "rejected by RANSAC"
          : "flagged by RANSAC, included in fallback fit";
      } else if (error > safeThreshold) {
        state = "included, residual above threshold";
      }
      item.textContent = `${pointName}: ${Number(error).toFixed(2)} px (${state})`;
      list.appendChild(item);
    });
  }

  clearCalibrationPointDiagnostics() {
    // Invalidate in-flight responses so a pre-edit callback cannot restore
    // obsolete rejection indices after the user starts dragging a point.
    this.calibrationRequestId++;
    this.calibrationFitState = "stale";
    this.rejectedPointIndices = [];
    if (this.camCanvas) {
      this.camCanvas.setCalibrationPointDiagnostics([], []);
    }
    if (this.viewport) {
      this.viewport.setCalibrationPointDiagnostics([], []);
    }
  }

  clearCalibrationFitStatus() {
    const diagnostics = document.getElementById("calibration-diagnostics");
    const summary = document.getElementById("calibration-fit-summary");
    const guidance = document.getElementById("calibration-geometry-guidance");
    const warningList = document.getElementById(
      "calibration-geometry-warnings",
    );
    const details = document.getElementById("calibration-fit-details");
    const errors = document.getElementById("calibration-point-errors");
    this.clearCalibrationPointDiagnostics();
    if (diagnostics) {
      diagnostics.hidden = true;
    }
    if (summary) {
      summary.textContent = "";
    }
    if (guidance) {
      guidance.hidden = true;
    }
    if (warningList) {
      warningList.replaceChildren();
    }
    if (details) {
      details.hidden = true;
      details.open = false;
    }
    if (errors) {
      errors.replaceChildren();
    }
  }

  getAcceptedCalibrationPointNames(camPoints) {
    const rejectedIndices = new Set(this.rejectedPointIndices);
    return Object.keys(camPoints).filter(
      (_, index) => !rejectedIndices.has(index),
    );
  }

  initializeTransforms(transforms, transformType) {
    if (transformType === "euler") {
      const pose = transforms.map((value) => Number(value));
      if (pose.length === 9 && pose.every(Number.isFinite)) {
        this.viewport.setCameraPoseFromEuler(
          pose.slice(0, 3),
          pose.slice(3, 6),
        );
        this.rememberCalibrationPose();
        this.projectionEnabled = true;
      }
      return;
    }

    this.addInitialCalibrationPoints(transforms, transformType);
  }

  addInitialCalibrationPoints(points, transformType) {
    if (transformType !== "3d-2d point correspondence") {
      return;
    }
    if (points.length % 5 === 0) {
      const splitPoint = (points.length / 5) * 2;
      for (let i = 0; i < splitPoint; i += 2) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        this.addSensorCalibrationPoint(x, y);
      }
      for (let i = splitPoint; i < points.length; i += 3) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        const z = parseFloat(points[i + 2]);
        this.viewport.addCalibrationPoint(x, y, z);
      }
    } else if (points.length % 2 === 0) {
      const splitPoint = points.length / 2;
      for (let i = 0; i < splitPoint; i += 2) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        this.addSensorCalibrationPoint(x, y);
      }
      for (let i = splitPoint; i < points.length; i += 2) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        this.viewport.addCalibrationPoint(x, y, 0);
      }
    }
  }

  addAutoCalibrationPoints(msg) {
    const number_of_apriltags = msg.calibration_points_2d.length;

    for (let i = 1; i <= number_of_apriltags; i++) {
      const cam_coord = msg.calibration_points_2d[i - 1];
      const map_coord = msg.calibration_points_3d[i - 1];

      this.addSensorCalibrationPoint(cam_coord[0], cam_coord[1]);
      this.viewport.addCalibrationPoint(
        map_coord[0],
        map_coord[1],
        map_coord[2],
      );
    }
  }

  clearCalibrationPoints() {
    this.pendingSensorPoints = [];
    this.camCanvas.clearCalibrationPoints();
    this.viewport.clearCalibrationPoints();
    this.projectionEnabled = false;
    // clearCalibrationFitStatus → clearCalibrationPointDiagnostics bumps
    // calibrationRequestId so any in-flight fit response is ignored.
    this.clearCalibrationFitStatus();
    this.calibrationFitState = "idle";
  }

  setupCalibrationParameterListeners() {
    // Intrinsics/distortion edits (and lock toggles) change the model that
    // produced the current RANSAC rejection set. Invalidate immediately so an
    // in-flight response cannot overwrite typed values, but do not auto-refit:
    // writing unlocked fields from a new response would wipe manual edits.
    // Moving a calibration point re-triggers calculateCalibrationIntrinsics.
    const invalidateFit = () => {
      this.clearCalibrationPointDiagnostics();
    };
    const selector =
      'input[name^="intrinsics_"], input[name^="distortion_"], input[id^="enabled_"]';
    $(selector).on("input", invalidateFit);
    $(selector).on("change", invalidateFit);
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

  setupSaveCameraButton() {
    $("#calibration_form").on("submit", (event) => {
      event.preventDefault();
      if (this.isPTZAwayFromHome()) {
        alert(PTZ_AWAY_MESSAGE);
        return;
      }
      if (!this.centerManualIntrinsics()) return;
      if (typeof document !== "undefined") {
        const cxField = document.getElementById("id_intrinsics_cx");
        const cyField = document.getElementById("id_intrinsics_cy");
        if (cxField) cxField.disabled = false;
        if (cyField) cyField.disabled = false;
      }

      const camPoints = this.getSensorCalibrationPoints();
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

      if (this.calibrationFitState === "pending") {
        alert("Please wait for the calibration fit to finish before saving.");
        return;
      }
      if (this.calibrationFitState === "failed") {
        alert(
          "The latest calibration fit failed. Adjust the point pairs and wait " +
            "for a successful fit before saving.",
        );
        return;
      }
      if (this.calibrationFitState === "stale") {
        alert(
          "The calibration fit is out of date. Move a calibration point " +
            "slightly (or wait for a pending fit) to refresh before saving.",
        );
        return;
      }

      if (this.isValidCalibration(camPoints, scenePoints)) {
        const acceptedNames = this.getAcceptedCalibrationPointNames(camPoints);
        if (acceptedNames.length < CALIBRATION_MIN_POINTS_FOR_FIT) {
          alert(
            "Saving the calibration requires at least " +
              `${CALIBRATION_MIN_POINTS_FOR_FIT} accepted point pairs after ` +
              "outlier rejection.\n\n" +
              `There are currently ${acceptedNames.length} accepted pairs ` +
              `(${this.rejectedPointIndices.length} rejected by RANSAC). ` +
              "Remove or adjust the rejected pairs and try again.",
          );
          return;
        }
        // Persist only pairs that were used in the fitted pose (exclude RANSAC rejects).
        const camPointsStr = acceptedNames
          .map((name) => camPoints[name])
          .map((point) => `${point[0]},${point[1]}`)
          .join(",");
        const scenePointsStr = acceptedNames
          .map((name) => scenePoints[name])
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
          "Saving the calibration requires matching point pairs with the same " +
            `names in each view (minimum ${CALIBRATION_MIN_POINTS_FOR_FIT}).\n\n` +
            `There are currently ${camPointCount} points in the camera ` +
            `view and ${scenePointCount} points in the scene view.`,
        );
      }
    });
  }

  getCameraPositionAndRotation(cameraMatrix, distCoeffs) {
    const camPoints = this.getSensorCalibrationPoints();
    const objectPoints = this.viewport.getCalibrationPoints();
    if (!(
      this.isValidCalibration(camPoints, objectPoints) &&
      (this.camCanvas.calibrationUpdated ||
        this.viewport.calibrationUpdated ||
        this.resolutionNeedsRefit)
    )) {
      return false;
    }

    let rvec = new cv.Mat();
    let tvec = new cv.Mat();
    let R = new cv.Mat();
    let imagePointsMat = null;
    let objectPointsMat = null;
    let cameraMatrixMat = null;
    let distCoeffsMat = null;

    try {
      // Convert imagePoints and objectPoints to cv.Mat, paired by name.
      const acceptedNames = this.getAcceptedCalibrationPointNames(camPoints);
      const camPointsArray = acceptedNames.map((name) => camPoints[name]);
      const objectPointsArray = acceptedNames.map((name) => objectPoints[name]);
      imagePointsMat = cv.matFromArray(
        camPointsArray.length,
        2,
        cv.CV_64F,
        camPointsArray.flat(),
      );
      objectPointsMat = cv.matFromArray(
        objectPointsArray.length,
        3,
        cv.CV_64F,
        objectPointsArray.flat(),
      );
      cameraMatrixMat = cv.matFromArray(3, 3, cv.CV_64F, cameraMatrix.flat());
      distCoeffsMat = cv.matFromArray(1, 5, cv.CV_64F, distCoeffs.flat());

      let computationMethod = cv.SOLVEPNP_ITERATIVE;
      // If we do not have coplanar points and fewer than 6 points, use SQPNP
      if (this.arePointsCoplanar(objectPointsArray) === false) {
        computationMethod = cv.SOLVEPNP_SQPNP;
      }
      const solved = cv.solvePnP(
        objectPointsMat,
        imagePointsMat,
        cameraMatrixMat,
        distCoeffsMat,
        rvec,
        tvec,
        false,
        computationMethod,
      );
      if (!solved) {
        return false;
      }
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
      this.rememberCalibrationPose();
      this.projectionEnabled = true;
      this.camCanvas.calibrationUpdated = false;
      this.viewport.calibrationUpdated = false;
      this.resolutionNeedsRefit = false;
      return true;
    } finally {
      rvec.delete();
      tvec.delete();
      R.delete();
      if (imagePointsMat) imagePointsMat.delete();
      if (objectPointsMat) objectPointsMat.delete();
      if (cameraMatrixMat) cameraMatrixMat.delete();
      if (distCoeffsMat) distCoeffsMat.delete();
    }
  }

  undistortAndProjectImage(
    image,
    cameraMatrix,
    distCoeffs,
    frameTimestamp,
    generation,
  ) {
    this.projectionImage.src = image;
    this.projectionImage.onload = () => {
      // Skip frames invalidated by PTZ motion while the image was decoding.
      if (!this.ptzFrameGate.accepts(frameTimestamp, generation)) return;
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
        frameTimestamp,
        generation,
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

  /**
   * Projects a camera frame onto the scene.
   * @param {string} image - Frame image URL.
   * @param {number[][]} cameraMatrix - Camera intrinsics matrix.
   * @param {string} frameTimestamp - Acquisition timestamp of the frame.
   * @param {number} generation - PTZ frame-gate generation when the frame arrived.
   */
  projectImage(
    image,
    cameraMatrix,
    frameTimestamp,
    generation = this.ptzFrameGate.generation,
  ) {
    if (this.projectionEnabled === false || this.ptzPoseValid === false) {
      this.viewport.setProjectionVisibility(false);
      return;
    }
    const accepts = () =>
      this.ptzPoseValid !== false &&
      this.ptzFrameGate.accepts(frameTimestamp, generation);
    // Frames from before the camera stopped, or for an earlier pose, are dropped.
    if (!accepts()) return;
    if (this.ptzLiveMatrix) {
      this.viewport.setCameraPose(this.ptzProjectionPose());
    }
    this.viewport.projectImage(image, cameraMatrix, accepts);
  }

  /**
   * The frame was captured at the live PTZ pose. Apply its offset from the stored
   * home pose to the calibration pose being previewed, so a newly fitted home
   * calibration stays visible while calibrating.
   * @returns {THREE.Matrix4} Projection camera matrix.
   */
  ptzProjectionPose() {
    const home =
      this.ptzHomePoseMatrix &&
      sceneFromCameraToCameraMatrix(this.ptzHomePoseMatrix);
    if (!this.calibrationPoseMatrix || !home) return this.ptzLiveMatrix;
    return this.calibrationPoseMatrix
      .clone()
      .multiply(home.invert())
      .multiply(this.ptzLiveMatrix);
  }

  // Records the calibration (home) pose just set on the projection camera.
  rememberCalibrationPose() {
    const camera = this.viewport.projectionCamera;
    camera.updateMatrix();
    this.calibrationPoseMatrix = camera.matrix.clone();
  }

  /**
   * Shows the frame from the live PTZ pose (display only; Save uses calibration points).
   * @param {Object} msg - Parsed PoseContext payload.
   * @param {string} sceneID - UID of the scene that owns the camera.
   * @param {string} calibrationVersion - PTZ calibration version of the camera.
   * @param {string} cameraUID - UID of the camera, used to load its stored home pose.
   */
  updatePTZPose(msg, sceneID, calibrationVersion, cameraUID) {
    this.loadPTZHomePose(cameraUID);
    this.ptzMoving = isPTZMoving(msg);
    this.ptzPositionUnknown = isPTZPositionUnknown(msg);
    let matrix = ptzPoseToCameraMatrix(msg, sceneID, calibrationVersion);
    this.ptzFrameGate.update(msg, Boolean(matrix), this.ptzMoving);
    this.ptzPoseExpiry.arm(matrix ? msg : null, () =>
      this.updatePTZPose(
        expiredPTZPoseContext(),
        sceneID,
        calibrationVersion,
        cameraUID,
      ),
    );
    let poseRows = matrix ? msg.pose.matrix_4x4 : null;
    if (!matrix && !this.ptzMoving) {
      // Position unknown but not moving (e.g. backlash not yet learned).
      if (this.ptzHomePoseMatrix === null) {
        // Home pose unavailable: behave as for a non-PTZ camera.
        this.ptzPoseValid = null;
        this.ptzLiveMatrix = null;
        this.ptzLivePoseMatrix = null;
        if (this.camCanvas) this.setPTZPointMapper("static", null, true);
        return;
      }
      poseRows = this.ptzHomePoseMatrix || null;
      matrix = poseRows && sceneFromCameraToCameraMatrix(poseRows);
    }
    this.ptzPoseValid = Boolean(matrix);
    this.ptzLivePoseMatrix = matrix ? poseRows : null;
    this.updatePTZCalibrationPoints();
    if (!this.viewport || ptzMatricesClose(matrix, this.ptzLiveMatrix)) {
      return;
    }
    // Hide the previous frame until one is captured at the new pose.
    this.ptzFrameGate.invalidate();
    this.viewport.setProjectionVisibility(false);
    if (!matrix) return;
    this.ptzLiveMatrix = matrix.clone();
    this.viewport.setCameraPose(this.ptzProjectionPose());
  }

  // The stored home pose is the reference the calibration points were placed in.
  loadPTZHomePose(cameraUID) {
    if (this.ptzHomeRequested || !this.viewport) {
      return;
    }
    this.ptzHomeRequested = true;
    this.viewport.restClient
      .getCamera(cameraUID)
      .then((response) => {
        const poseMatrix = response.content && response.content.pose_matrix;
        this.ptzHomePoseMatrix =
          response.statusCode === 200 && Array.isArray(poseMatrix)
            ? poseMatrix
            : null;
      })
      .catch(() => {
        this.ptzHomePoseMatrix = null;
      })
      .finally(() => {
        if (this.ptzHomePoseMatrix === null) {
          console.warn("PTZ home pose unavailable; showing stored points.");
        }
        this.updatePTZCalibrationPoints();
      });
  }

  // Shows the stored (home) calibration points where they appear in the live PTZ frame.
  updatePTZCalibrationPoints() {
    if (!this.camCanvas || this.ptzPoseValid === null) {
      return;
    }
    // Hide while moving or while the home pose loads; without it keep static points.
    if (!this.ptzPoseValid || this.ptzHomePoseMatrix === undefined) {
      this.setPTZPointMapper("hidden", null, false);
      return;
    }
    if (this.ptzHomePoseMatrix === null) {
      this.setPTZPointMapper("static", null, true);
      return;
    }
    const intrinsics = ["fx", "fy", "cx", "cy"].map((key) =>
      parseFloat($(`#id_intrinsics_${key}`).val()),
    );
    const distortion = ["k1", "k2", "p1", "p2", "k3"].map((key) =>
      parseFloat($(`#id_distortion_${key}`).val()),
    );
    const key = JSON.stringify([
      this.ptzLivePoseMatrix,
      intrinsics,
      distortion,
    ]);
    if (key === this.ptzPointMapperKey) return;
    if (this.ptzPendingPoints && key === this.ptzPendingPoints.key) return;
    const mapper = createPTZPointMapper(
      this.ptzHomePoseMatrix,
      this.ptzLivePoseMatrix,
      intrinsics,
      distortion,
    );
    if (!Number.isFinite(this.ptzFrameGate.notBefore)) {
      this.setPTZPointMapper(key, mapper, true);
      return;
    }
    // The video lags the pose: show the moved points with the first frame
    // captured after the camera stopped (see applyPendingPTZPoints).
    this.setPTZPointMapper("pending", null, false);
    this.ptzPendingPoints = {
      key,
      mapper,
      notBefore: this.ptzFrameGate.notBefore,
    };
  }

  /**
   * Applies reprojected points held back until the camera stopped.
   * @param {string} frameTimestamp - Acquisition timestamp of the displayed frame.
   */
  applyPendingPTZPoints(frameTimestamp) {
    const pending = this.ptzPendingPoints;
    if (!pending) return;
    const frameTime = Date.parse(frameTimestamp);
    if (Number.isFinite(frameTime) && frameTime < pending.notBefore) return;
    this.setPTZPointMapper(pending.key, pending.mapper, true);
  }

  // Positioning publishes several times per second; redraw only on a change.
  setPTZPointMapper(key, mapper, visible) {
    this.ptzPendingPoints = null;
    if (key === this.ptzPointMapperKey) return;
    this.ptzPointMapperKey = key;
    this.camCanvas.setPointMapper(mapper, visible);
  }

  // Auto calibration and Save are for the home pose, not the current frame.
  isPTZAwayFromHome() {
    if (this.ptzMoving || this.ptzPositionUnknown) return true;
    if (!this.ptzPoseValid || !this.ptzHomePoseMatrix) return false;
    return isPTZAwayFromHomePose(
      this.ptzHomePoseMatrix,
      this.ptzLivePoseMatrix,
    );
  }

  getSensorResolution() {
    const resolution = [
      Number($("#id_width").val()),
      Number($("#id_height").val()),
    ];
    return resolution.every((value) => Number.isInteger(value) && value > 0)
      ? resolution
      : this.camCanvas.getImageSize();
  }

  getPreviewScale() {
    const sensor = this.getSensorResolution();
    return this.camCanvas
      .getImageSize()
      .map((size, index) => size / sensor[index]);
  }

  getSensorCalibrationPoints() {
    const scale = this.getPreviewScale();
    return Object.fromEntries(
      Object.entries(this.camCanvas.getCalibrationPoints()).map(
        ([name, point]) => [
          name,
          point.map((value, index) => value / scale[index]),
        ],
      ),
    );
  }

  addSensorCalibrationPoint(x, y) {
    if (!this.camCanvas.getImageSize().every((value) => value > 0)) {
      (this.pendingSensorPoints ||= []).push([x, y]);
      return;
    }
    const scale = this.getPreviewScale();
    this.camCanvas.addCalibrationPoint(x * scale[0], y * scale[1]);
  }

  flushSensorCalibrationPoints() {
    const pending = this.pendingSensorPoints || [];
    this.pendingSensorPoints = [];
    for (const [x, y] of pending) this.addSensorCalibrationPoint(x, y);
  }

  updateSensorResolution(resolution) {
    if (!resolution) return;
    const dimensions = Array.isArray(resolution)
      ? resolution
      : [resolution.width, resolution.height];
    if (
      dimensions.length !== 2 ||
      !dimensions.every((value) => Number.isInteger(value) && value > 0)
    ) {
      console.warn("Ignoring invalid sensor resolution:", resolution);
      return;
    }
    const previous = this.getSensorResolution();
    dimensions.forEach((value, index) =>
      $(`#id_${index === 0 ? "width" : "height"}`).val(value),
    );
    if (dimensions.some((value, index) => value !== previous[index])) {
      this.isResolutionUpdated = this.resolutionNeedsRefit = true;
    }
  }

  updateCalibrationViews(
    image,
    cameraMatrix,
    distCoeffs,
    resolution,
    frameTimestamp,
  ) {
    // PTZ callers pass only a frame timestamp as the 4th argument.
    if (
      frameTimestamp === undefined &&
      (typeof resolution === "string" || resolution === undefined)
    ) {
      frameTimestamp = resolution;
      resolution = undefined;
    }
    const generation = this.ptzFrameGate.generation;
    this.updateSensorResolution(resolution);
    this.camCanvas.updateImageSrc(image, () => {
      this.applyPendingPTZPoints(frameTimestamp);
      this.updateLoadedCalibrationViews(
        image,
        cameraMatrix,
        distCoeffs,
        frameTimestamp,
        generation,
      );
    });
  }

  centerManualIntrinsics(cameraMatrix) {
    const size = this.camCanvas.getImageSize();
    if (!size.every((value) => Number.isInteger(value) && value > 0)) {
      console.warn(
        "Manual calibration requires a loaded image with valid dimensions:",
        size,
      );
      return false;
    }
    let changed = size.some(
      (value, index) => value !== this.getSensorResolution()[index],
    );
    this.updateSensorResolution(size);
    for (const [index, axis] of ["cx", "cy"].entries()) {
      const selector = `#id_intrinsics_${axis}`;
      const center = size[index] / 2;
      if (Number($(selector).val()) !== center) {
        changed = true;
        this.isResolutionUpdated = this.resolutionNeedsRefit = true;
      }
      $(selector).val(center);
      if (typeof document !== "undefined") {
        const field = document.getElementById(`id_intrinsics_${axis}`);
        if (field) field.readOnly = true;
        const lock = document.getElementById(`enabled_intrinsics_${axis}`);
        if (lock) {
          lock.checked = true;
          lock.disabled = true;
        }
      }
      if (Array.isArray(cameraMatrix?.[index])) {
        cameraMatrix[index][2] = center;
      }
    }
    if (changed && this.calibrationFitState === "pending") {
      this.calibrationRequestId++;
      this.calibrationFitState = "idle";
    }
    return true;
  }

  updateLoadedCalibrationViews(
    image,
    cameraMatrix,
    distCoeffs,
    frameTimestamp,
    generation,
  ) {
    if (!this.centerManualIntrinsics(cameraMatrix)) return;
    this.flushSensorCalibrationPoints();
    const size = this.camCanvas.getImageSize();
    $("#detected_resolution").val(`${size[0]} x ${size[1]}`);
    const scale = this.getPreviewScale();
    const previewMatrix = cameraMatrix.map((row, index) =>
      row.map((value) =>
        index < 2 ? Number(value) * scale[index] : Number(value),
      ),
    );
    if (
      this.calibrationFitState !== "pending" &&
      this.calibrationFitState !== "failed" &&
      this.calibrationFitState !== "stale" &&
      (this.camCanvas.calibrationUpdated ||
        this.viewport.calibrationUpdated ||
        this.resolutionNeedsRefit) &&
      this.isValidCalibration(
        this.camCanvas.getCalibrationPoints(),
        this.viewport.getCalibrationPoints(),
      )
    ) {
      this.calculateCalibrationIntrinsics();
    }
    if (distCoeffs.some((coeff) => coeff !== 0)) {
      this.undistortAndProjectImage(
        image,
        previewMatrix,
        distCoeffs,
        frameTimestamp,
        generation,
      );
    } else {
      this.projectImage(image, previewMatrix, frameTimestamp, generation);
    }
  }
}
