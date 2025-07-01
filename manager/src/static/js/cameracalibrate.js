// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

/**
 * @file cameracalibrate.js
 * @description This file defines the ConvergedCameraCalibration class, which provides
 * functions for managing the camera calibration process through a camera and a scene viewport
 */

'use strict';

import * as THREE from '/static/assets/three.module.js';
import { GLTFLoader } from '/static/examples/jsm/loaders/GLTFLoader.js';
import { CamCanvas } from "/static/js/camcanvas.js";
import { Viewport } from "/static/js/viewport.js";
import {
  APP_NAME,
  CMD_CAMERA,
  INITIAL_PROJECTION_OPACITY,
  MAX_COPLANAR_DETERMINANT,
  MAX_INTRINSICS_UPDATE_WAIT_TIME,
  FX, FY, CX, CY,
  K1, K2, P1, P2, K3,
  REST_URL
} from "/static/js/constants.js";
import {
  compareIntrinsics,
  resizeRendererToDisplaySize,
  waitUntil
} from "/static/js/utils.js";

export class ConvergedCameraCalibration {
  constructor() {
    this.camCanvas = null;
    this.viewport = null;
    this.client = null;
    this.isUpdatedInPercebro = false;
    this.projectionEnabled = false;

    // Used for storing undistorted image for projection
    this.projectionImage = new Image();
    this.projectionCanvas = $("<canvas></canvas>")[0];
    this.projectionCtx = this.projectionCanvas.getContext("2d", { willReadFrequently: true });

    this.textureLoader = new THREE.TextureLoader();
  }

  /**
   * Sets the MQTT client to re-use the client defined at the upper level. Adds an event
   * listener to the client to check if the intrinsics have been updated in Percebro.
   * @param {mqtt.Client} client - The MQTT client to use for communication
   * @param {string} cameraTopic - The topic for the camera image
   */
  setMqttClient(client, cameraTopic) {
    this.client = client;

    this.client.on('message', (topic, message) => {
      // Uses the topic for the camera image, as it is the only topic that sends intrinsics
      // when there are no detections in the scene
      if (topic === cameraTopic) {
        let msg = JSON.parse(message);
        const intrinsics = this.getIntrinsics();

        this.isUpdatedInPercebro = compareIntrinsics(
          intrinsics["intrinsics"], msg.intrinsics.flat(), intrinsics["distortion"], msg.distortion);
      }
    });
  }

  initializeCamCanvas(canvasElement, imageSrc) {
    this.camCanvas = new CamCanvas(canvasElement, imageSrc);
    // FIXME: Find a better way to do these event listeners which require interacting with both
    // the camCanvas and viewport
    this.camCanvas.canvas.addEventListener("mouseup", (event) => {
      this.calculateCalibrationIntrinsics();
    });
    this.camCanvas.canvas.addEventListener("dblclick", (event) => {
      this.calculateCalibrationIntrinsics();
    });
    this.camCanvas.canvas.addEventListener("mousemove", (event) => {
      if(this.camCanvas.isDragging) {
        this.projectionEnabled = false;
      }
    });
  }

  initializeViewport(canvas, scale, sceneID, authToken) {
    const gltfLoader = new GLTFLoader();
    const renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: true
    });
    const viewport = new Viewport(canvas, scale, sceneID, authToken, gltfLoader, renderer);
    this.viewport = viewport;

    viewport.loadMap().then(() => {
      viewport.initializeScene();

      function animate() {
        if (resizeRendererToDisplaySize(viewport.renderer)) {
          const canvas = viewport.renderer.domElement;
          viewport.perspectiveCamera.aspect = canvas.clientWidth / canvas.clientHeight;
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

      viewport.renderer.domElement.addEventListener("mouseup", (event) => {
        this.calculateCalibrationIntrinsics();
      });
      viewport.renderer.domElement.addEventListener("dblclick", (event) => {
        this.calculateCalibrationIntrinsics();
      });
      viewport.renderer.domElement.addEventListener("mousemove", (event) => {
        if(viewport.isDragging) {
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

    return v1[0] * (v2[1] * v3[2] - v2[2] * v3[1]) -
           v1[1] * (v2[0] * v3[2] - v2[2] * v3[0]) +
           v1[2] * (v2[0] * v3[1] - v2[1] * v3[0]);
  }

  arePointsCoplanar(points) {
    // Only need to check for lengths of 4 or 5
    if (points.length === 5) {
      for (let i = 0; i < points.length; i++) {
        const subset = points.filter((_, index) => index !== i);
        if (Math.abs(this.#calculateDeterminant(subset) > MAX_COPLANAR_DETERMINANT)) {
          return false;
        }
      }
    } else if (points.length === 4) {
      return Math.abs(this.#calculateDeterminant(points)) < MAX_COPLANAR_DETERMINANT;
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
    const matchingNames = camPointNames.filter(name => mapPointNames.includes(name));

    if (matchingNames.length >= 4 && camPointNames.length === mapPointNames.length) {
      return true;
    }
    return false;
  }

  getIntrinsics() {
    return {
      'intrinsics': {
        'fx': parseFloat($("#id_intrinsics_fx").val()),
        'fy': parseFloat($("#id_intrinsics_fy").val()),
        'cx': parseFloat($("#id_intrinsics_cx").val()),
        'cy': parseFloat($("#id_intrinsics_cy").val())
      },
      'distortion': {
        'k1': parseFloat($("#id_distortion_k1").val()),
        'k2': parseFloat($("#id_distortion_k2").val()),
        'p1': parseFloat($("#id_distortion_p1").val()),
        'p2': parseFloat($("#id_distortion_p2").val()),
        'k3': parseFloat($("#id_distortion_k3").val())
      }
    };
  }

  calculateCalibrationIntrinsics() {
    const camPoints = this.camCanvas.getCalibrationPoints();
    const mapPoints = this.viewport.getCalibrationPoints(true);
    if (this.isValidCalibration(camPoints, mapPoints) && Object.keys(camPoints).length >= 6) {
      const intrinsicCheckboxes = $('input[type="checkbox"][name^="enabled_"]');
      const fixIntrinsics = {};
      intrinsicCheckboxes.each(function() {
        const name = this.name.split("_")[2];
        fixIntrinsics[name] = this.checked;
      });

      // Collect intrinsic and distortion data
      const intrinsicData = [];
      const distortionData = [];
      let fx, fy, cx, cy;

      $('input[name^="intrinsics_"]').each(function() {
        if (this.name === "intrinsics_fx") fx = parseFloat(this.value);
        if (this.name === "intrinsics_fy") fy = parseFloat(this.value);
        if (this.name === "intrinsics_cx") cx = parseFloat(this.value);
        if (this.name === "intrinsics_cy") cy = parseFloat(this.value);
      });

      // Format the intrinsic data into a matrix
      intrinsicData.push([fx, 0, cx]);
      intrinsicData.push([0, fy, cy]);
      intrinsicData.push([0, 0, 1]);

      $('input[name^="distortion_"]').each(function() {
        distortionData.push(parseFloat(this.value));
      });

      const data = {
        camPoints: Object.values(camPoints),
        mapPoints: Object.values(mapPoints),
        fixIntrinsics: fixIntrinsics,
        intrinsics: intrinsicData,
        distortion: distortionData,
        imageSize: this.camCanvas.getImageSize()
      };

      $.ajax({
        url: `${REST_URL}/calculateintrinsics`,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Token ${$("#auth-token").val()}`
        },
        data: JSON.stringify(data),
        contentType: "application/json",
        success: function(response) {
          // Fill out the corresponding intrinsic and distortion fields if they are not disabled
          const intrinsicMtx = response["mtx"].flat();
          $('input[name^="intrinsics_"]').each(function() {
            if (!$(this).prop("disabled")) {
              if (this.name === "intrinsics_fx") this.value = intrinsicMtx[FX];
              if (this.name === "intrinsics_fy") this.value = intrinsicMtx[FY];
              if (this.name === "intrinsics_cx") this.value = intrinsicMtx[CX];
              if (this.name === "intrinsics_cy") this.value = intrinsicMtx[CY];
            }
          });
          $('input[name^="distortion_"]').each(function() {
            if (!$(this).prop("disabled")) {
              if (this.name === "distortion_k1") this.value = response["dist"][K1];
              if (this.name === "distortion_k2") this.value = response["dist"][K2];
              if (this.name === "distortion_p1") this.value = response["dist"][P1];
              if (this.name === "distortion_p2") this.value = response["dist"][P2];
              if (this.name === "distortion_k3") this.value = response["dist"][K3];
            }
          });
        },
        error: function(error) {
          // If invalid values are passed, print the error text
          console.log(error.responseText);
        }
      });
    }
  }

  addInitialCalibrationPoints(points, transformType) {
    if (transformType !== "3d-2d point correspondence") {
      return;
    }
    if (points.length % 5 === 0) {
      const splitPoint = (points.length / 5) * 2;
      for (let i = 0; i < splitPoint; i+=2) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        this.camCanvas.addCalibrationPoint(x, y);
      }
      for (let i = splitPoint; i < points.length; i+=3) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        const z = parseFloat(points[i + 2]);
        this.viewport.addCalibrationPoint(x, y, z);
      }
    } else if (points.length % 2 === 0) {
      const splitPoint = points.length / 2;
      for (let i = 0; i < splitPoint; i+=2) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        this.camCanvas.addCalibrationPoint(x, y);
      }
      for (let i = splitPoint; i < points.length; i+=2) {
        const x = parseFloat(points[i]);
        const y = parseFloat(points[i + 1]);
        this.viewport.addCalibrationPoint(x, y, 0);
      }
    }
  }

  addAutocalibrationPoints(msg) {
    const number_of_apriltags = msg.calibration_points_2d.length;

    for (let i = 1; i <= number_of_apriltags; i++) {
      const cam_coord = msg.calibration_points_2d[i - 1];
      const map_coord = msg.calibration_points_3d[i - 1];

      this.camCanvas.addCalibrationPoint(cam_coord[0], cam_coord[1]);
      this.viewport.addCalibrationPoint(map_coord[0], map_coord[1], map_coord[2]);
    }
  }

  clearCalibrationPoints() {
    this.camCanvas.clearCalibrationPoints();
    this.viewport.clearCalibrationPoints();
    this.projectionEnabled = false;
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
      localStorage.setItem('opacity', opacityValue);
    });
  }

  setupSaveCameraButton() {
    $("#calibration_form").on("submit", (event) => {
      event.preventDefault();
      const camPoints = this.camCanvas.getCalibrationPoints();
      const scenePoints = this.viewport.getCalibrationPoints();
      if (this.isValidCalibration(camPoints, scenePoints)) {
        const camPointsStr = Object.values(camPoints)
          .map(point => `${point[0]},${point[1]}`)
          .join(",");
        const scenePointsStr = Object.values(scenePoints)
          .map(point => `${point[0]},${point[1]},${point[2]}`)
          .join(",");
        $("#id_transforms").val(`${camPointsStr},${scenePointsStr}`);
        $("#id_transform_type").val("3d-2d point correspondence");

        if (this.client) {
          const intrinsicData = {
            'updatecamera': this.getIntrinsics()
          }
          const topic = APP_NAME + CMD_CAMERA + $("#sensor_id").val();
          this.client.publish(topic, JSON.stringify(intrinsicData), { qos: 1});
          // Wait for data to be updated in percebro
          // FIXME: Unify with code in scenecamera.js
          waitUntil(() => this.isUpdatedInPercebro, 100, MAX_INTRINSICS_UPDATE_WAIT_TIME)
          .then(() => {
            // If intrinsics are unlocked, inform the user to remove the override flag
            if ($("#id_intrinsics_fx").prop("disabled") === false &&
                $("#id_intrinsics_fy").prop("disabled") === false) {
              alert("Camera updated. Ensure \"--override-saved-intrinsics\" is not set for " +
                    "this camera in docker-compose.yml to have these changes persist.");
            } else {
              alert("Camera updated");
            }
            $("#calibration_form")[0].submit();
          })
          .catch((error) => {
            alert("Failed to update camera intrinsics in Percebro. Please try again.\n\n" +
                  "If you keep getting this error, please check the documentation for " +
                  "known issues.");
          });
        } else {
          $("#calibration_form")[0].submit();
        }
      } else {
        alert("Saving the calibration requires an equal number of calibration points in each " +
              "view (minimum 4).\n\n" +
              `There are currently ${Object.keys(camPoints).length} points in the camera ` +
              `view and ${Object.keys(scenePoints).length} points in the scene view.`);
      }
    });
  }

  getCameraPositionAndRotation(cameraMatrix, distCoeffs) {
    const camPoints = this.camCanvas.getCalibrationPoints();
    const objectPoints = this.viewport.getCalibrationPoints();
    if (this.isValidCalibration(camPoints, objectPoints) &&
        (this.camCanvas.calibrationUpdated || this.viewport.calibrationUpdated)) {
      let rvec = new cv.Mat();
      let tvec = new cv.Mat();
      let R = new cv.Mat();


      // Convert imagePoints and objectPoints to cv.Mat
      const camPointsArray = Object.values(camPoints);
      const objectPointsArray = Object.values(objectPoints);
      const imagePointsMat = cv.matFromArray(camPointsArray.length, 2, cv.CV_64F, camPointsArray.flat());
      const objectPointsMat = cv.matFromArray(objectPointsArray.length, 3, cv.CV_64F, objectPointsArray.flat());
      let cameraMatrixMat = cv.matFromArray(3, 3, cv.CV_64F, cameraMatrix.flat());
      let distCoeffsMat = cv.matFromArray(1, 5, cv.CV_64F, distCoeffs.flat());

      let computationMethod = cv.SOLVEPNP_ITERATIVE;
      // If we do not have coplanar points and fewer than 6 points, use SQPNP
      if (this.arePointsCoplanar(objectPointsArray) === false) {
        computationMethod = cv.SOLVEPNP_SQPNP;
      }
      // Prepare other necessary parameters
      cv.solvePnP(objectPointsMat, imagePointsMat, cameraMatrixMat, distCoeffsMat, rvec, tvec, false, computationMethod);
      cv.Rodrigues(rvec, R);
      let T = new THREE.Matrix4();
      //OpenCV to OpenGL coordinate system alignment requires negating rows 2 and 3 in transform matrix
      //https://stackoverflow.com/questions/44375149/opencv-to-opengl-coordinate-system-transform
      T.set(R.data64F[0], R.data64F[1], R.data64F[2], tvec.data64F[0],
        -R.data64F[3], -R.data64F[4], -R.data64F[5], -tvec.data64F[1],
        -R.data64F[6], -R.data64F[7], -R.data64F[8], -tvec.data64F[2],
        0, 0, 0, 1);
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
      const cameraMatrixMat = cv.matFromArray(3, 3, cv.CV_64F, cameraMatrix.flat());
      const distCoeffsMat = cv.matFromArray(1, 5, cv.CV_64F, distCoeffs.flat());
      // 3x3 identity matrix
      const identityMatrix = cv.matFromArray(3, 3, cv.CV_64F, [1, 0, 0, 0, 1, 0, 0, 0, 1]);
      cv.initUndistortRectifyMap(cameraMatrixMat, distCoeffsMat, identityMatrix, cameraMatrixMat, new cv.Size(w, h), 5, map_x, map_y);
      const undistortedImage = new cv.Mat();
      cv.remap(distortedImage, undistortedImage, map_x, map_y, cv.INTER_LINEAR);

      // Put undistorted image on canvas to use with projection later
      const imageData = new ImageData(new Uint8ClampedArray(undistortedImage.data), undistortedImage.cols, undistortedImage.rows);
      this.projectionCtx.putImageData(imageData, 0, 0);

      this.projectImage(this.projectionCanvas.toDataURL("image/jpeg"), cameraMatrix);

      distortedImage.delete();
      undistortedImage.delete();
      map_x.delete();
      map_y.delete();
      cameraMatrixMat.delete();
      distCoeffsMat.delete();
      identityMatrix.delete();
    }
  }

  projectImage(image, cameraMatrix) {
    if (this.projectionEnabled === false) {
      this.viewport.setProjectionVisibility(false);
      return;
    }
    this.viewport.projectImage(image, cameraMatrix);
  }

  updateCalibrationViews(image, cameraMatrix, distCoeffs) {
    this.camCanvas.updateImageSrc(image);
    this.getCameraPositionAndRotation(cameraMatrix, distCoeffs);
    if (distCoeffs.some(coeff => coeff !== 0)) {
      this.undistortAndProjectImage(image, cameraMatrix, distCoeffs);
    } else {
      this.projectImage(image, cameraMatrix);
    }
  }
}
