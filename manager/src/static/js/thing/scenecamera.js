// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import * as THREE from "/static/assets/three.module.js";
import CustomCameraHelper from "/static/js/customcamerahelper.js";
import ThingControls from "/static/js/thing/controls/thingcontrols.js";
import thingTransformControls from "/static/js/thing/controls/thingtransformcontrols.js";
import validateInputControls from "/static/js/thing/controls/validateinputcontrols.js";
import Toast from "/static/js/toast.js";
import {
  CMD_CAMERA,
  IMAGE_CAMERA,
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
} from "/static/js/constants.js";
import { compareIntrinsics } from "/static/js/utils.js";

const DEFAULT_DIAGONAL_FOV = 70;
const DEFAULT_RESOLUTION = { w: 640, h: 480 };
const DEFAULT_INTRINSICS = {
  fx: computeFyFromDFOV(DEFAULT_DIAGONAL_FOV, DEFAULT_RESOLUTION),
  fy: computeFyFromDFOV(DEFAULT_DIAGONAL_FOV, DEFAULT_RESOLUTION),
  cx: DEFAULT_RESOLUTION.w / 2,
  cy: DEFAULT_RESOLUTION.h / 2,
};

const DEFAULT_DISTORTION = [0, 0, 0, 0, 0];
const MAX_CALIB_POINTS = 4;
const DEFAULT_CAMERA_NAME = "new-camera";
const DEFAULT_CAMERA_UID = undefined;
const MAX_CALIB_WAIT_TIME = 200000;

//VFOV = 2 * atan(tan((DFOV/2)*h/sqrt(pow(w, 2)+pw(h,2))))
function computeVerticalFOVFromDiagonal(dFOV, resolution) {
  const hypotenuse = Math.sqrt(
    resolution.w * resolution.w + resolution.h * resolution.h,
  );
  const temp =
    Math.tan(THREE.MathUtils.degToRad(dFOV / 2)) * (resolution.h / hypotenuse);
  return 2 * THREE.MathUtils.radToDeg(Math.atan(temp));
}

function computeDiagonalFOV(cx, cy, fy) {
  return (
    2 * THREE.MathUtils.radToDeg(Math.atan(Math.sqrt(cx * cx + cy * cy) / fy))
  );
}

function computeVerticalFOVFromFy(fy, resolution) {
  return THREE.MathUtils.radToDeg(2 * Math.atan(resolution.h / (2 * fy)));
}

function computeFyFromDFOV(dFOV, resolution) {
  const vfov = computeVerticalFOVFromDiagonal(dFOV, resolution);
  return resolution.h / 2 / Math.tan(THREE.MathUtils.degToRad(vfov / 2));
}

function constructIntrinsicsMatrix(intrinsics, resolution) {
  if (["fx", "fy", "cx", "cy"].every((key) => key in intrinsics)) {
    return [
      [intrinsics["fx"], 0, intrinsics["cx"]],
      [0, intrinsics["fy"], intrinsics["cy"]],
      [0, 0, 1],
    ];
  } else if ("fov" in intrinsics) {
    return [
      [computeFyFromDFOV(intrinsics["fov"], resolution), 0, resolution.w / 2],
      [0, computeFyFromDFOV(intrinsics["fov"], resolution), resolution.h / 2],
      [0, 0, 1],
    ];
  }

  return [
    [intrinsics[0], 0, intrinsics[2]],
    [0, intrinsics[1], intrinsics[3]],
    [0, 0, 1],
  ];
}

function constructDistortionArray(distortion) {
  return [
    distortion["k1"],
    distortion["k2"],
    distortion["p1"],
    distortion["p2"],
    distortion["k3"],
  ];
}

//we need multiple instances of scenecamera and hence need a class
export default class SceneCamera extends THREE.Object3D {
  constructor(params) {
    super();
    Object.assign(this, thingTransformControls);
    Object.assign(this, validateInputControls);
    this.cameraUID = params.uid;
    this.name = params.name;
    this.fovEnabled = false;
    this.isStoredInDB = params.isStoredInDB;
    this.isUpdatedInDB = false;
    this.isUpdatedInPercebro = false;
    this.cameraCapture = null;
    this.intrinsics =
      "intrinsics" in params ? params.intrinsics : DEFAULT_INTRINSICS;
    this.distortion =
      "distortion" in params ? params.distortion : DEFAULT_DISTORTION;
    this.resolution =
      "resolution" in params
        ? { w: params.resolution[0], h: params.resolution[1] }
        : DEFAULT_RESOLUTION;
    this.cameraMatrix = cv.matFromArray(
      3,
      3,
      cv.CV_64F,
      constructIntrinsicsMatrix(this.intrinsics, this.resolution).flat(),
    );
    this.distCoeffs = cv.matFromArray(
      1,
      5,
      cv.CV_64F,
      constructDistortionArray(this.distortion),
    );
    this.imagePoints = null;
    this.calibPoints = new THREE.Group();
    this.cameraPosition =
      "translation" in params
        ? new THREE.Vector3(...params.translation)
        : new THREE.Vector3(0, 0, 0);
    this.cameraRotation =
      "rotation" in params
        ? new THREE.Euler(
            ...params.rotation.map(function (item) {
              return THREE.MathUtils.degToRad(item);
            }),
          )
        : new THREE.Euler(0, 0, 0);
    this.add(this.calibPoints);
    this.previousName = this.name;
    this.projectionColor = "#FFFFFF";
    this.aspectRatio = 4.0 / 3.0;
    this.toast = Toast();
    this.calibToast = null;
    this.flipCoordSystem = true;
    this.isStaff = params.isStaff;
    if (this.cameraPosition && this.cameraRotation) {
      this.addCamera();
    } else {
      this.toast.showToast(
        `Failed to load position/rotation for ${this.name}. Check intrinsics config in percebro.`,
        "warning",
      );
    }
  }

  addCamera() {
    const vfov = computeVerticalFOVFromFy(
      this.cameraMatrix.data64F[FY],
      this.resolution,
    );
    this.sceneCamera = new THREE.PerspectiveCamera(
      vfov,
      this.resolution.w / this.resolution.h,
      0.1,
      10,
    );
    this.sceneCamera.position.copy(this.cameraPosition);
    this.sceneCamera.rotation.copy(this.cameraRotation); //in Radians
    this.textPos = new THREE.Vector3(0, 0, 0);
    this.add(this.sceneCamera);
    //pose from scenescape is y-down. threejs is y-up.
    this.togglePoseYupYdown(this.sceneCamera);
    this.sceneCameraHelper = new CustomCameraHelper(this.sceneCamera, 1);
    this.add(this.sceneCameraHelper);
  }

  addObject(params) {
    this.drawObj = params.drawObj;
    if (this.sceneCamera) {
      this.drawObj
        .createTextObject(this.name, this.textPos)
        .then((textMesh) => {
          this.sceneCamera.add(textMesh);
        });
    }
    this.sceneMesh = params.sceneMesh;
    this.scene = params.scene;
    this.renderer = params.renderer;
    this.cameraControls = new ThingControls(this);
    this.cameraControls.addToScene();
    this.addControlPanel(params.camerasFolder);
    this.addDragControls(params.sceneViewCamera, params.orbitControls, () => {
      this.calibPoints.clear();
      this.imagePoints = null;
      this.executeOnControl("fov", (control) => {
        control[0].domElement.classList.add("disabled");
      });
      this.fovEnabled = false;
    });

    const fields = [
      "name",
      "scene camera",
      "show camera",
      "project frame",
      "pause video",
      "opacity",
      "toggle rotate/translate",
      "pos X",
      "pos Y",
      "pos Z",
      "rot X",
      "rot Y",
      "rot Z",
    ];
    if (this.isStaff === null) {
      this.disableFields(fields);
    }

    this.sceneViewCamera = params.sceneViewCamera;
    this.setViewCamera = params.setViewCamera;
    this.currentCameras = params.currentThings;
  }

  reloadCamera() {
    this.remove(this.sceneCamera);
    this.remove(this.sceneCameraHelper);
    this.addCamera();
    if (this.sceneCamera) {
      this.drawObj
        .createTextObject(this.name, this.textPos)
        .then((textMesh) => {
          this.sceneCamera.add(textMesh);
        });
    }
    this.resetTransformObject();
    return;
  }

  updateDistortion(distortion) {
    if (distortion) {
      this.distCoeffs = cv.matFromArray(
        1,
        5,
        cv.CV_64F,
        constructDistortionArray(distortion),
      );
      this.distortionFolder.children[0].$input.value =
        this.distCoeffs.data64F[K1];
    }
    return;
  }
  updateIntrinsics(intrinsics) {
    let newIntrinsics = this.intrinsics;
    if ("fx" in intrinsics) {
      newIntrinsics = intrinsics;
    } else {
      newIntrinsics = {
        fx: intrinsics[0][0],
        fy: intrinsics[1][1],
        cx: intrinsics[0][2],
        cy: intrinsics[1][2],
      };
    }
    if (JSON.stringify(newIntrinsics) !== JSON.stringify(this.intrinsics)) {
      this.intrinsics = newIntrinsics;
      this.cameraMatrix = cv.matFromArray(
        3,
        3,
        cv.CV_64F,
        constructIntrinsicsMatrix(this.intrinsics, this.resolution).flat(),
      );
      this.reloadCamera();
      this.intrinsicsFolder.children[0].$input.value =
        this.cameraMatrix.data64F[FX];
      this.intrinsicsFolder.children[1].$input.value =
        this.cameraMatrix.data64F[FY];
      this.intrinsicsFolder.children[2].$input.value =
        this.cameraMatrix.data64F[CX];
      this.intrinsicsFolder.children[3].$input.value =
        this.cameraMatrix.data64F[CY];
    }

    this.executeOnControl("fov", (control) => {
      let dfov = computeDiagonalFOV(
        this.cameraMatrix.data64F[CX],
        this.cameraMatrix.data64F[CY],
        this.cameraMatrix.data64F[FY],
      );
      if (dfov !== control[0].getValue()) {
        control[0].setValue(
          computeDiagonalFOV(
            this.cameraMatrix.data64F[CX],
            this.cameraMatrix.data64F[CY],
            this.cameraMatrix.data64F[FY],
          ),
        );
      }
    });

    return;
  }

  addControlPanel(camerasFolder) {
    this.controlsFolder = camerasFolder.addFolder(this.name);
    this.controlsFolder.$title.setAttribute("id", this.name + "-control-panel");
    this.addStatusIndicator();

    this.projectFrame = false;
    let panelSettings = {
      name: this.name === DEFAULT_CAMERA_NAME ? "" : this.name,
      opacity: 100,
      fov: computeDiagonalFOV(
        this.cameraMatrix.data64F[CX],
        this.cameraMatrix.data64F[CY],
        this.cameraMatrix.data64F[FY],
      ),
      "scene camera": false,
      "calibration points visibility":
        this.calibPoints && this.calibPoints.visible,
      "project frame": this.projectFrame,
      "pause video": false,
      fx: this.cameraMatrix.data64F[FX],
      fy: this.cameraMatrix.data64F[FY],
      cx: this.cameraMatrix.data64F[CX],
      cy: this.cameraMatrix.data64F[CY],
      k1: this.distCoeffs.data64F[K1],
      k2: this.distCoeffs.data64F[K2],
      p1: this.distCoeffs.data64F[P1],
      p2: this.distCoeffs.data64F[P2],
      k3: this.distCoeffs.data64F[K3],
      "auto calibrate": function () {
        this.autoCalibrate();
      }.bind(this),
      "show camera": true,
      color: "#ffffff",
      "aspect ratio": this.aspectRatio,
      save: function () {
        this.saveSettings();
      }.bind(this),
      delete: function () {
        this.removeFromScene(camerasFolder);
      }.bind(this),
    };

    let control = this.controlsFolder.add(panelSettings, "name").onChange(
      function (value) {
        this.prevName = this.name;
        this.name = value;
        this.validateField("name", () => {
          return this.name === "" || this.name === DEFAULT_CAMERA_NAME;
        });
      }.bind(this),
    );
    control.$widget.firstChild.id = this.name.concat("-", "name");

    control = this.controlsFolder.add(panelSettings, "scene camera").onChange(
      function (setAsDefault) {
        const camera = setAsDefault ? this.sceneCamera : this.sceneViewCamera;
        this.setViewCamera(camera);
      }.bind(this),
    );
    control.$widget.firstChild.id = this.name.concat("-", "scene-camera");

    control = this.controlsFolder.add(panelSettings, "show camera").onChange(
      function (value) {
        this.visible = value;
      }.bind(this),
    );

    control = this.controlsFolder
      .add(panelSettings, "calibration points visibility")
      .onChange(
        function (visibility) {
          this.calibPoints.visible = visibility;
        }.bind(this),
      );
    control.$widget.firstChild.id = this.name.concat("-", "calibration");
    if (!(this.calibPoints && this.calibPoints.children.length > 0))
      control.hide();

    control = this.controlsFolder.add(panelSettings, "project frame").onChange(
      function (visibility) {
        this.projectFrame = visibility;
        if (this.projectFrame) {
          this.mqttClient.publish(
            this.appName + CMD_CAMERA + this.name,
            "getimage",
          );
        }
        if (this.cameraCapture != null) {
          this.cameraCapture.visible = visibility;
        }
        visibility ? this.add(this.calibPoints) : this.remove(this.calibPoints);
      }.bind(this),
    );
    control.$widget.firstChild.id = this.name.concat("-", "project-frame");

    control = this.controlsFolder.add(panelSettings, "pause video").onChange(
      function (visibility) {
        this.pauseVideo = visibility;
        if (!this.pauseVideo && this.projectFrame) {
          this.mqttClient.publish(
            this.appName + CMD_CAMERA + this.name,
            "getimage",
          );
        }
      }.bind(this),
    );
    control.$widget.firstChild.id = this.name.concat("-", "pause-video");

    control = this.controlsFolder
      .add(panelSettings, "opacity", 0, 100, 1)
      .onChange(
        function (weight) {
          if (this.cameraCapture) this.cameraCapture.opacity = weight / 100.0;
        }.bind(this),
      );
    control.$input.id = this.name.concat("-", "opacity");

    control = this.controlsFolder.add(panelSettings, "fov", 1, 180, 1).onChange(
      function (fov) {
        this.fovEnabled = true;
        let newIntrinsics = constructIntrinsicsMatrix(
          { fov: fov },
          this.resolution,
        );
        let fx = newIntrinsics[0][0];
        let fy = newIntrinsics[1][1];
        let cx = newIntrinsics[0][2];
        let cy = newIntrinsics[1][2];
        newIntrinsics = { fx: fx, fy: fy, cx: cx, cy: cy };
        this.updateIntrinsics(newIntrinsics);
        this.setCameraVerticalFOV();
        this.performCameraCalib();
      }.bind(this),
    );

    control.$input.id = this.name.concat("-", "fov");
    this.executeOnControl("fov", (control) => {
      control[0].domElement.classList.add("disabled");
    });

    control = this.controlsFolder.addColor(panelSettings, "color").onChange(
      function (value) {
        this.projectionColor = value.toUpperCase();
        this.generateProjectionFrame();
      }.bind(this),
    );

    control = this.controlsFolder
      .add(panelSettings, "aspect ratio")
      .onFinishChange(
        function (value) {
          this.aspectRatio = value;
          this.generateProjectionFrame();
        }.bind(this),
      );

    control = this.addPoseControls(panelSettings);
    control = this.addIntrinsicsControls(control, panelSettings);
    control = this.addDistortionControls(control, panelSettings);

    if (this.isStaff) {
      control = this.controlsFolder.add(panelSettings, "save");
      control.$button.id = this.name.concat("-", "save-camera");
      control = this.controlsFolder.add(panelSettings, "delete");
      control.$button.id = this.name.concat("-", "delete-camera");
      control = this.controlsFolder.add(panelSettings, "auto calibrate");
      control.domElement.classList.add("disabled");
    }

    if (this.isStoredInDB) control.domElement.classList.add("disabled");
    if (this.name === "" || this.name === DEFAULT_CAMERA_NAME)
      this.addFieldWarning("name");

    this.controlsFolder.close();
    this.controlsFolder.$title.addEventListener(
      "click",
      ((event) => {
        camerasFolder.setSelectedCamera(this);
      }).bind(this),
    );

    this.generateProjectionFrame();
  }

  createSolidColorPng(color, aspectRatio) {
    var canvas = document.createElement("canvas");
    canvas.height = 240;
    canvas.width = canvas.height * aspectRatio;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/png");
  }

  generateProjectionFrame() {
    if (this.interval) clearInterval(this.interval);
    const image = this.createSolidColorPng(
      this.projectionColor,
      this.aspectRatio,
    );
    this.interval = setInterval(
      (() => {
        this.projectCameraCapture(image, {}, false);
      }).bind(this),
      33,
    );
  }

  enableAutoCalibration(value) {
    if (value) {
      this.executeOnControl("auto calibrate", (control) => {
        control[0].domElement.classList.remove("disabled");
      });
    } else {
      this.executeOnControl("auto calibrate", (control) => {
        control[0].domElement.classList.add("disabled");
      });
    }
  }

  hideAutoCalibrateButton() {
    this.executeOnControl("auto calibrate", (control) => {
      control[0].domElement.hidden = true;
    });
  }

  addStatusIndicator() {
    let statusIndicator = document.createElement("span");
    statusIndicator.classList.add("offline");
    this.controlsFolder.$title.appendChild(statusIndicator);
  }

  addDistortionControls(control, panelSettings) {
    this.distortionFolder = this.controlsFolder.addFolder("Distortion");
    this.distortionFolder.$title.setAttribute("id", this.name + "-distortion");

    control = this.distortionFolder.add(panelSettings, "k1").onFinishChange(
      function (value) {
        this.updateSaveButton();
      }.bind(this),
    );
    control.$input.id = this.name.concat("-", "k1");
    control.domElement.classList.add("disabled");
    this.distortionFolder.close();
    return control;
  }

  setCameraVerticalFOV() {
    if (this.resolution) {
      this.sceneCamera.fov = computeVerticalFOVFromFy(
        this.cameraMatrix.data64F[FY],
        this.resolution,
      );
      this.sceneCamera.updateProjectionMatrix();
      if (this.cameraCapture) {
        this.cameraCapture.camera = this.sceneCamera;
        this.cameraCapture.project(this.mesh);
      }
    }
  }

  setCameraAspectRatio() {
    this.sceneCamera.aspect =
      this.cameraMatrix.data64F[CX] / this.cameraMatrix.data64F[CY];
    this.sceneCamera.updateProjectionMatrix();
    if (this.cameraCapture) {
      this.cameraCapture.camera = this.sceneCamera;
      this.cameraCapture.project(this.mesh);
    }
  }

  setPoseSuffix() {
    if (this.cameraCapture) this.cameraCapture.project(this.mesh);
  }

  get transformObject() {
    return this.sceneCamera;
  }

  addIntrinsicsControls(control, panelSettings) {
    this.intrinsicsFolder = this.controlsFolder.addFolder("Intrinsics");
    this.intrinsicsFolder.$title.setAttribute("id", this.name + "-intrinsics");

    control = this.intrinsicsFolder.add(panelSettings, "fx");
    control.$input.id = this.name.concat("-", "fx");
    control.domElement.classList.add("disabled");

    control = this.intrinsicsFolder.add(panelSettings, "fy");
    control.$input.id = this.name.concat("-", "fy");
    control.domElement.classList.add("disabled");

    control = this.intrinsicsFolder.add(panelSettings, "cx");
    control.$input.id = this.name.concat("-", "cx");
    control.domElement.classList.add("disabled");

    control = this.intrinsicsFolder.add(panelSettings, "cy");
    control.$input.id = this.name.concat("-", "cy");
    control.domElement.classList.add("disabled");

    this.intrinsicsFolder.close();
    return control;
  }

  async removeFromScene(camerasFolder) {
    const isConfirmed = window.confirm(
      `Are you sure you want to remove "${this.name}"?`,
    );

    if (isConfirmed) {
      camerasFolder.unsetSelectedCamera(this);
      this.scene.remove(this);
      this.deleteFromSceneCameras(this.name);

      if (this.isStoredInDB) {
        let deleteResponse = await this.restclient.deleteCamera(this.cameraUID);

        if (deleteResponse.statusCode == "200") {
          this.controlsFolder.destroy();
          this.toast.showToast(
            "Camera has been deleted from the database!",
            "success",
          );
        } else {
          this.scene.add(this);
          this.toast.showToast(
            "Failed to delete the camera from the database!",
            "danger",
          );
        }
      } else {
        this.controlsFolder.destroy();
        this.toast.showToast("Unsaved camera has been removed!", "success");
      }
    } else {
      this.toast.showToast("Camera removal canceled", "danger");
    }
  }

  updateSaveButton() {
    if (this.validateInputs()) {
      this.executeOnControl("save", (control) =>
        control[0].domElement.classList.remove("disabled"),
      );
    }
  }

  validateInputs() {
    return this.name !== "" && this.name !== DEFAULT_CAMERA_NAME;
  }

  setMQTTClient(client, appName) {
    this.mqttClient = client;
    this.appName = appName;

    // Subscribe to camera image topic to check if intrinsics have been updated in percebro
    this.mqttClient.on("message", (topic, message) => {
      if (topic === this.appName + IMAGE_CAMERA + this.name) {
        let msg = JSON.parse(message);

        this.isUpdatedInPercebro = compareIntrinsics(
          this.intrinsics,
          msg.intrinsics.flat(),
          this.distortion,
          msg.distortion,
        );
      }
    });
  }

  autoCalibrate() {
    this.enableAutoCalibration(false);
    this.toast.showToast(
      "Performing auto camera calibration for " + this.name + "...",
      "information",
      this.name + "-Calibrate",
      MAX_CALIB_WAIT_TIME,
    );
    this.calibToast = document.getElementById(this.name + "-Calibrate");
    this.calibToast.children[0].children[1].disabled = true;
    this.mqttClient.publish(this.appName + CMD_CAMERA + this.name, "localize");
  }

  getCalibNotifyElement() {
    return this.calibToast;
  }

  async saveSettings() {
    let camera = this.sceneCamera.clone();
    //convert to y-down before saving
    this.togglePoseYupYdown(camera);

    let cameraData = {
      sensor_id: this.cameraUID,
      name: this.name,
      scene: this.sceneID,
      translation: [...camera.position],
      rotation: [camera.rotation.x, camera.rotation.y, camera.rotation.z].map(
        function (item) {
          return THREE.MathUtils.radToDeg(item);
        },
      ),
      scale: [1, 1, 1],
      transform_type: "euler",
    };

    if (this.cameraUID) {
      // Publish intrinsics to MQTT to update percebro
      const intrinsicData = {
        updatecamera: {
          translation: cameraData["translation"],
          rotation: cameraData["rotation"],
          intrinsics: this.intrinsics,
          distortion: this.distortion,
        },
      };
      const topic = this.appName + CMD_CAMERA + this.cameraUID;
      this.mqttClient.publish(topic, JSON.stringify(intrinsicData));
      // Wait for data to be updated in percebro
      let waitTime = 0;
      while (
        !this.isUpdatedInPercebro &&
        waitTime < MAX_INTRINSICS_UPDATE_WAIT_TIME
      ) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        waitTime += 100;
      }
      if (!this.isUpdatedInPercebro) {
        const message =
          `New camera intrinsics did not update in percebro within ` +
          `${MAX_INTRINSICS_UPDATE_WAIT_TIME}ms.`;
        this.toast.showToast(message, "danger");
      }
    }

    let textObject = this.sceneCamera.getObjectByName(
      "textObject_" + this.previousName,
    );
    if (this.isStoredInDB) await this.updateExistingCamera(cameraData);
    else {
      await this.createNewCamera(cameraData, textObject);
    }
    this.updateCameras(this.previousName, this.name, textObject);
    this.executeOnControl("save", (control) =>
      control[0].domElement.classList.add("disabled"),
    );
  }

  deleteFromSceneCameras(cameraName) {
    if (this.currentCameras[cameraName]) {
      delete this.currentCameras[cameraName];
    }
  }
  updateCameras(oldCamName, newCamName, textObject) {
    if (this.isUpdatedInDB) {
      let camName = this.name;
      if (this.currentCameras[oldCamName] && oldCamName !== newCamName) {
        camName = newCamName;
        oldCamName = newCamName;

        this.currentCameras[newCamName] = this.currentCameras[oldCamName];
        delete this.currentCameras[oldCamName];
      } else {
        this.previousName = this.name;
      }

      if (this.sceneCamera) {
        this.sceneCamera.remove(textObject);
        this.drawObj
          .createTextObject(this.name, this.textPos)
          .then((textMesh) => {
            this.sceneCamera.add(textMesh);
          });
      }
    }
    this.controlsFolder.title(newCamName);
    this.controlsFolder.$title.setAttribute(
      "id",
      newCamName + "-control-panel",
    );
    this.addStatusIndicator();
  }

  async createNewCamera(cameraData, textObject) {
    let createResponse = await this.restclient.createCamera(cameraData);

    if (createResponse.statusCode === 201) {
      this.isStoredInDB = true;
      this.cameraUID = createResponse.content.uid;
      if (this.sceneCamera) {
        this.sceneCamera.remove(textObject);
        this.drawObj
          .createTextObject(this.name, this.textPos)
          .then((textMesh) => {
            this.sceneCamera.add(textMesh);
          });
      }
      this.previousName = this.name;
      for (const camObj of this.currentCameras[DEFAULT_CAMERA_UID]) {
        if (this.name === camObj.name) {
          this.currentCameras[this.name] = camObj;
          var index = this.currentCameras[DEFAULT_CAMERA_UID].indexOf(camObj);
          if (index > -1) {
            this.currentCameras[DEFAULT_CAMERA_UID].splice(index, 1);
          }
          break;
        }
      }
      this.toast.showToast("Camera setting has been saved!", "success");
    } else if (createResponse.statusCode === 400) {
      console.log(createResponse.errors);
      this.toast.showToast(
        "Something went wrong. Please make sure the camera name you entered is unique.",
        "danger",
      );
    } else {
      console.log(createResponse.errors);
      this.toast.showToast(
        "Something went wrong. Failed to save camera setting. Please try again!",
        "danger",
      );
    }
  }

  async updateExistingCamera(cameraData) {
    let updateResponse = await this.restclient.updateCamera(
      this.cameraUID,
      cameraData,
    );
    if (updateResponse.statusCode === 200) {
      this.isUpdatedInDB = true;
      this.toast.showToast("Camera setting has been updated!", "success");
    } else if (updateResponse.statusCode === 400) {
      console.log(updateResponse.errors);
      this.isUpdatedInDB = false;
      this.toast.showToast(
        "Something went wrong. Please make sure the camera name you entered is unique.",
        "danger",
      );
    } else {
      console.log(updateResponse.errors);
      this.isUpdatedInDB = false;
      this.toast.showToast(
        "Something went wrong. Failed to update camera setting. Please try again!",
        "danger",
      );
    }
  }

  //image: input frame to be projection mapped
  //scene: mesh onto which we will project
  projectCameraCapture(image, data, online = true) {
    if (online) {
      clearInterval(this.interval);
      this.executeOnControl("aspect ratio", (control) => {
        if (control[0]) control[0].destroy();
      });
      this.executeOnControl("color", (control) => {
        if (control[0]) control[0].destroy();
      });
      this.showCameraOnline();
    }

    if (this.sceneCamera && this.projectFrame && !this.pauseVideo) {
      const loader = new THREE.TextureLoader();
      loader.load(
        image,
        (texture) => {
          this.resolution = { w: texture.image.width, h: texture.image.height };
          this.sceneCamera.aspect = texture.image.width / texture.image.height;
          this.sceneCamera.fov = computeVerticalFOVFromFy(
            this.cameraMatrix.data64F[FY],
            this.resolution,
          );
          this.sceneCamera.updateProjectionMatrix();
          if (this.cameraCapture === null) {
            [this.cameraCapture, this.mesh] =
              this.drawObj.createProjectionMaterial(
                this.sceneCamera,
                this.sceneMesh,
                texture,
              );
            // scene is the group. We add the mesh to the group because we want it to move together.
            this.add(this.mesh);
          } else {
            this.cameraCapture.texture = texture;
            this.cameraCapture.project(this.mesh);
          }
        },
        undefined,
        function (err) {
          console.log("Error loading texture!", err);
        },
      );
    }
  }

  showCameraOnline() {
    const statusIndicator =
      this.controlsFolder.$title.querySelector(".offline");
    if (statusIndicator) {
      statusIndicator.classList.replace("offline", "online");
      this.executeOnControl("project frame", (control) =>
        control[0].$input.removeAttribute("disabled"),
      );
    }
  }

  updateImagePoints() {
    let fourCalib = [...this.calibPoints.children];
    let imgPoints = [];
    let calibVec = new THREE.Vector3();
    var widthHalf = 0.5 * this.resolution.w;
    var heightHalf = 0.5 * this.resolution.h;
    //initial reprojection onto image plane of the 4-points
    for (const calibPoint of fourCalib) {
      let { x, y, z } = calibPoint.position;
      calibVec.set(x, y, z);
      calibVec.project(this.sceneCamera);
      calibVec.x = calibVec.x * widthHalf + widthHalf;
      calibVec.y = -(calibVec.y * heightHalf) + heightHalf;
      imgPoints.push(calibVec.x, calibVec.y);
    }

    this.imagePoints = cv.matFromArray(
      MAX_CALIB_POINTS,
      2,
      cv.CV_64F,
      imgPoints,
    );
  }

  performCameraCalib() {
    let fourCalib = [...this.calibPoints.children];
    if (fourCalib.length === MAX_CALIB_POINTS) {
      // Define 3D and 2D points
      let objPoints = [];
      for (const calibPoint of fourCalib) {
        let { x, y, z } = calibPoint.position;
        objPoints.push(x, y, z);
      }

      let T = this.computeTransformMatrix(objPoints);
      let euler = new THREE.Euler();
      euler.setFromRotationMatrix(T);
      let position = new THREE.Vector3();
      position.setFromMatrixPosition(T);
      this.setPosition(position, false);
      this.setRotation(euler);
    }
  }

  computeTransformMatrix(objPoints) {
    const objectPoints = cv.matFromArray(
      MAX_CALIB_POINTS,
      3,
      cv.CV_64F,
      objPoints,
    );

    let rvec = new cv.Mat();
    let tvec = new cv.Mat();
    let R = new cv.Mat();
    try {
      //solvepnp_sqpnp is used as it works for 4 non-coplanar points and is faster than solvepnp_epnp.
      //solvepnp default method needs 6 points (uses direct linear transform) when they are non-coplanar
      //and Levenberg Marquadt requires 4 points to be coplanar.
      cv.solvePnP(
        objectPoints,
        this.imagePoints,
        this.cameraMatrix,
        this.distCoeffs,
        rvec,
        tvec,
        false,
        cv.SOLVEPNP_SQPNP,
      );
    } catch (error) {
      console.error(error);
      return;
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

    return T;
  }

  onClick(open) {
    this.setTransformControlVisibility(true);
    this.add(this.calibPoints);
    this.executeOnControl("calibration points visibility", (control) => {
      control[0].setValue(true);
    });
    if (open) this.controlsFolder.open();
  }

  onDoubleClick(sphere) {
    if (this.calibPoints.children.length < MAX_CALIB_POINTS) {
      if (this.projectFrame) this.calibPoints.add(sphere);
      if (this.calibPoints.children.length === 1) {
        this.executeOnControl("calibration points visibility", (control) => {
          control[0].setValue(true);
          control[0].show();
        });
      }
    }
    if (this.calibPoints.children.length === MAX_CALIB_POINTS) {
      if (this.imagePoints === null) {
        this.executeOnControl("fov", (control) => {
          control[0].domElement.classList.remove("disabled");
        });
        this.updateImagePoints();
      }
    }
  }

  onRightClick(sphere) {
    this.calibPoints.remove(sphere);
    if (this.calibPoints.children.length === 0) {
      this.executeOnControl("calibration points visibility", (control) => {
        control[0].setValue(false);
        control[0].hide();
      });
    }
    if (this.calibPoints.children.length < MAX_CALIB_POINTS) {
      this.executeOnControl("fov", (control) => {
        control[0].domElement.classList.add("disabled");
      });
      this.fovEnabled = false;
    }
    this.imagePoints = null; // it will get refreshed on next point move
  }

  unselect() {
    this.setTransformControlVisibility(false);
    this.calibPoints.visible = false;
    this.executeOnControl("calibration points visibility", (control) => {
      control[0].setValue(false);
    });
    this.controlsFolder.close();
  }
}
