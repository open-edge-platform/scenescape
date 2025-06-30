// SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

"use strict";

import * as THREE from "/static/assets/three.module.js";
import { OrbitControls } from "/static/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "/static/examples/jsm/loaders/GLTFLoader.js";
import { GUI } from "/static/examples/jsm/libs/lil-gui.module.min.js";
import Stats from "/static/examples/jsm/libs/stats.module.js";
import AssetManager from "/static/js/assetmanager.js";
import CameraManager from "/static/js/thing/managers/cameramanager.js";
import RegionManager from "/static/js/thing/managers/regionmanager.js";
import SensorManager from "/static/js/thing/managers/sensormanager.js";
import TripwireManager from "/static/js/thing/managers/tripwiremanager.js";
import { SetupInteractions } from "/static/js/interactions.js";
import Scene from "/static/js/thing/scene.js";
import { Draw } from "/static/js/draw.js";
import Toast from "/static/js/toast.js";
import {
  initializeOpencv,
  resizeRendererToDisplaySize,
  checkWebSocketConnection,
} from "/static/js/utils.js";
import * as CONSTANTS from "/static/js/constants.js";
function main() {
  THREE.Object3D.DEFAULT_UP = new THREE.Vector3(0, 0, 1);
  let invisibleObject = new THREE.Object3D();

  //Camera related variables
  var { waitUntil, cvLoaded } = initializeOpencv();

  const canvas = document.getElementById("scene");
  const sceneID = document.getElementById("scene-id").value;
  const isStaff = document.getElementById("is-staff");
  const sceneName = document.getElementById("scene-name").value;
  const renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    alpha: true,
    antialias: true,
  });
  const appName = "scenescape";
  let toast = Toast();

  // Set up scene cameras and set default camera
  const fov = 40;
  const aspect = canvas.width / canvas.height;
  const near = 0.1;
  const far = 2000;
  const perspectiveCamera = new THREE.PerspectiveCamera(fov, aspect, near, far);
  const orthographicCamera = new THREE.OrthographicCamera(
    0,
    1,
    1,
    0,
    near,
    far,
  );
  const drawObj = new Draw();

  const scene = new THREE.Scene();
  scene.add(invisibleObject);
  const axesHelper = new THREE.AxesHelper(10);
  scene.add(axesHelper);

  // Camera variable to handle the current view
  let sceneViewCamera = perspectiveCamera;
  scene.add(sceneViewCamera);

  function setViewCamera(camera) {
    sceneViewCamera = camera;
  }

  const gltfLoader = new GLTFLoader();

  let showTrackedObjects = true;
  //Setup control panel
  const panel = new GUI({ width: 310 });
  const panelSettings = {
    "show tracked objects": showTrackedObjects,
  };
  panel.domElement.id = "panel-3d-controls";
  panel
    .add(panelSettings, "show tracked objects")
    .onChange(function (visibility) {
      showTrackedObjects = visibility;
      assetManager.hideMarks();
    }).$widget.id = "tracked-objects-button";

  const orbitControls = new OrbitControls(
    perspectiveCamera,
    renderer.domElement,
  );
  const raycaster = new THREE.Raycaster();
  raycaster.params.Points.threshold = 0.01;
  const interactions = SetupInteractions(
    scene,
    renderer,
    raycaster,
    orbitControls,
    sceneViewCamera,
  );

  const camerasFolder = panel.addFolder("Camera Settings");
  const tripwiresFolder = panel.addFolder("Tripwires Settings");
  const regionsFolder = panel.addFolder("Regions Settings");
  const sensorsFolder = panel.addFolder("Sensors Settings");

  camerasFolder.setSelectedCamera = interactions.setSelectedCamera;
  camerasFolder.unsetSelectedCamera = interactions.unsetSelectedCamera;
  let cameraManager = null;

  let sceneThingManagers = {
    things: {
      camera: {
        manager: CameraManager,
        renderer: renderer,
        sceneViewCamera: sceneViewCamera,
        orbitControls: orbitControls,
        setViewCamera: setViewCamera,
        camerasFolder: camerasFolder,
      },
      tripwire: {
        manager: TripwireManager,
        tripwireFolder: tripwiresFolder,
        color: "#00ff00",
        height: 0.3,
      },
      region: {
        manager: RegionManager,
        regionsFolder: regionsFolder,
        color: "#ff0000",
        height: 0.3,
        opacity: 0.4,
      },
      sensor: {
        manager: SensorManager,
        regionsFolder: sensorsFolder,
        color: "#0000ff",
        height: 0.3,
        opacity: 0.4,
      },
    },
  };

  // Ambient scene lighting
  const ambientColor = 0x707070; // Soft white
  const ambientLight = new THREE.AmbientLight(ambientColor);
  scene.add(ambientLight);

  const sceneBoundingBox = new THREE.Box3();

  let assetManager, client;
  async function loadThings() {
    let things = Object.keys(sceneThingManagers["things"]);
    await waitUntil(() => {
      return cvLoaded;
    });
    sceneThingManagers.things.camera.sceneMesh = getMeshToProjectOn();
    for (const thing of things) {
      sceneThingManagers["things"][thing]["drawObj"] = drawObj;
      sceneThingManagers["things"][thing]["scene"] = scene;
      let thingManager = new sceneThingManagers["things"][thing]["manager"](
        sceneID,
      );
      thingManager.setPrivilege(isStaff);
      await thingManager.load(sceneThingManagers["things"][thing]);
      sceneThingManagers["things"][thing].obj = thingManager;
    }

    if (isStaff) {
      addSceneControls();
    }
    for (const thing of things) {
      if (thing !== "camera") {
        sceneThing.loadChildAnalytics(sceneThingManagers, thing);
      }
    }

    connectMQTT();

    const checkboxes = panel.domElement.querySelectorAll(
      'input[type="checkbox"',
    );
    for (const checkbox of checkboxes) {
      checkbox.classList.add("lil-gui-toggle");
    }
  }

  const sceneThing = new Scene(
    sceneID,
    scene,
    panel,
    perspectiveCamera,
    orthographicCamera,
    renderer,
    toast,
    orbitControls,
    axesHelper,
    isStaff,
  );
  sceneThing.loadMap(gltfLoader, loadThings, sceneBoundingBox);

  function addSceneControls() {
    const panelSettings = {
      "add camera": function () {
        toast.showToast("Please enter a camera name before saving the camera.");
        addCamera(undefined, "new-camera");
      },
    };

    const control = camerasFolder.add(panelSettings, "add camera");
  }

  function setViewCamera(camera) {
    sceneViewCamera = camera;
  }

  function addCamera(cameraUID, cameraName) {
    let newCamera = {
      uid: cameraUID,
      name: cameraName,
      isStoredInDB: false,
      translation: [0, 0, 0],
      rotation: [0, 0, 0],
    };
    let params = sceneThingManagers.things.camera;
    cameraManager = sceneThingManagers["things"]["camera"]["obj"];
    cameraManager.add(newCamera);

    if (cameraManager.sceneThings.hasOwnProperty(undefined)) {
      for (const camObj of cameraManager.sceneThings[undefined]) {
        if (camObj.name === cameraName) {
          camObj.addObject(params);
          break;
        }
      }
    }

    const checkboxes = panel.domElement.querySelectorAll(
      'input[type="checkbox"',
    );
    for (const checkbox of checkboxes) {
      checkbox.classList.add("lil-gui-toggle");
    }
  }

  // MQTT Client
  async function connectMQTT() {
    // MQTT management (see https://github.com/mqttjs/MQTT.js)
    let brokerField = document.getElementById("broker");

    if (typeof brokerField != "undefined" && brokerField != null) {
      // Set broker value to the hostname of the current page
      // since broker runs on web server by default
      initializeMQTTBroker(brokerField);

      const urlInsecure =
        "wss://" + window.location.hostname + "/mqtt-insecure";
      const urlSecure = "wss://" + window.location.hostname + "/mqtt";
      const promises = [
        checkWebSocketConnection(urlInsecure), // Check insecure port
        checkWebSocketConnection(urlSecure), // Check secure port
      ];

      const results = await Promise.allSettled(promises);

      let openPort = null;

      results.forEach((result) => {
        if (result.status === "fulfilled") {
          openPort = result.value;
        }
      });

      if (openPort) {
        if (openPort === urlInsecure) {
          $("#broker").val(urlInsecure);
        }
        console.log("Attempting to connect to " + $("#broker").val());
        client = mqtt.connect($("#broker").val());

        client.on("connect", () => {
          console.log("Connected to " + $("#broker").val());
          client.subscribe(appName + CONSTANTS.IMAGE_CAMERA + "+");
          console.log(
            "Subscribed to " + (appName + CONSTANTS.IMAGE_CAMERA + "+"),
          );
          client.subscribe(appName + CONSTANTS.CMD_DATABASE);
          console.log("Subscribed to " + (appName + CONSTANTS.CMD_DATABASE));
          client.subscribe(appName + CONSTANTS.DATA_CAMERA + "+/+");
          console.log(
            "Subscribed to " + (appName + CONSTANTS.DATA_CAMERA + "+/+"),
          );

          if (sceneThing.isParent) {
            console.log(
              "Subscribed to " +
                (appName + CONSTANTS.EVENT + "/+" + "/" + sceneName + "/+/+"),
            );
            client.subscribe(
              appName + CONSTANTS.EVENT + "/+" + "/" + sceneName + "/+/+",
            );
          }
          cameraManager = sceneThingManagers["things"]["camera"]["obj"];
          for (const key in cameraManager.sceneCameras) {
            if (key !== "undefined") {
              cameraManager.sceneCameras[key].setMQTTClient(client, appName);
            }
          }

          autoCalibrationSetup();
        });
      }
    }

    client.on("message", (topic, data) => {
      handleMQTTMessage(topic, data);
    });

    client.on("error", (e) => {
      console.log("MQTT error: " + e);
    });

    assetManager = AssetManager(scene, subscribeToTracking);
    assetManager.loadAssets(gltfLoader);
    enableLiveView();
  }

  function autoCalibrationSetup() {
    if (document.getElementById("camera_calib_strategy").value == "Manual") {
      for (const key in cameraManager.sceneCameras) {
        if (key !== "undefined") {
          cameraManager.sceneCameras[key].hideAutoCalibrateButton();
        }
      }
    } else {
      client.subscribe(appName + CONSTANTS.SYS_AUTOCALIB_STATUS);
      console.log("Subscribed to " + CONSTANTS.SYS_AUTOCALIB_STATUS);
      client.publish(appName + CONSTANTS.SYS_AUTOCALIB_STATUS, "isAlive");
      client.subscribe(appName + CONSTANTS.CMD_AUTOCALIB_SCENE + sceneID);
      console.log("Subscribed to " + CONSTANTS.CMD_AUTOCALIB_SCENE + sceneID);
      for (const key in cameraManager.sceneCameras) {
        var pose_topic = appName + CONSTANTS.DATA_AUTOCALIB_CAM_POSE + key;
        client.subscribe(pose_topic);
        console.log("Subscribed to " + CONSTANTS.DATA_AUTOCALIB_CAM_POSE + key);
      }
    }
  }

  function handleMQTTMessage(topic, data) {
    let msg = {};
    try {
      msg = JSON.parse(data);
    } catch (error) {
      msg = String(data);
    }

    if (topic.includes(CONSTANTS.DATA_REGULATED)) {
      if (showTrackedObjects) {
        // Plot the marks
        assetManager.plot(msg);
      }
    } else if (topic.includes(CONSTANTS.CMD_DATABASE)) {
      cameraManager.refresh(client, appName + CONSTANTS.CMD_CAMERA);
    } else if (topic.includes(CONSTANTS.IMAGE_CAMERA)) {
      const id = topic.split("camera/")[1];
      cameraManager = sceneThingManagers["things"]["camera"]["obj"];
      if (cameraManager && cameraManager.sceneCameras.hasOwnProperty(id)) {
        cameraManager.sceneCameras[id].projectCameraCapture(
          "data:image/png;base64," + msg.image,
          msg,
        );
        if (
          cameraManager.sceneCameras[id].projectFrame &&
          !cameraManager.sceneCameras[id].pauseVideo
        ) {
          client.publish(appName + CONSTANTS.CMD_CAMERA + id, "getimage");
        }
      }
    } else if (topic.includes(CONSTANTS.DATA_CAMERA)) {
      const id = topic.split("/")[4];
      cameraManager = sceneThingManagers["things"]["camera"]["obj"];
      if (cameraManager && cameraManager.sceneCameras.hasOwnProperty(id)) {
        cameraManager.sceneCameras[id].updateDistortion(msg.distortion);
        if (cameraManager.sceneCameras[id].fovEnabled === false) {
          cameraManager.sceneCameras[id].updateIntrinsics(msg.intrinsics);
        }
      }
    } else if (topic.includes(CONSTANTS.EVENT)) {
      let analyticsName = topic.split("/")[2];

      const childData = {
        name: msg["metadata"]["title"],
        points: msg["metadata"]["points"],
        area: msg["metadata"]["area"],
      };

      if (msg["metadata"]["fromSensor"]) {
        analyticsName = "sensor";
      }

      if ("radius" in msg["metadata"]) {
        childData["radius"] = msg["metadata"]["radius"];
        childData["x"] = msg["metadata"]["x"];
        childData["y"] = msg["metadata"]["y"];
      }

      const analyticsParams = sceneThingManagers.things[analyticsName];
      const currentThings = analyticsParams.obj.sceneThings;

      if (childData["name"] in currentThings) {
        const analyticsClass = analyticsParams.obj.thingObjects();

        const tempChildData = new analyticsClass[analyticsName](childData);
        tempChildData.height =
          sceneThingManagers["things"][analyticsName]["height"];
        tempChildData.setPoints();

        if (
          JSON.stringify(tempChildData.points) !==
          JSON.stringify(currentThings[childData["name"]].points)
        ) {
          currentThings[childData["name"]].updateShape(childData);
        }
      } else {
        analyticsParams.obj.add(childData);
        analyticsParams.obj.update(0, analyticsParams);
      }
    } else if (topic.includes(CONSTANTS.SYS_AUTOCALIB_STATUS)) {
      if (msg === "running") {
        //processing scene map. Show spinner.
        client.publish(
          appName + CONSTANTS.CMD_AUTOCALIB_SCENE + sceneID,
          "register",
        );
      }
    } else if (topic.includes(CONSTANTS.CMD_AUTOCALIB_SCENE)) {
      if (msg !== "register") {
        if (msg.status === "success") {
          for (const key in cameraManager.sceneCameras) {
            if (key !== "undefined") {
              if (isStaff) {
                cameraManager.sceneCameras[key].enableAutoCalibration(true);
              }
            }
          }
        } else if (msg.status == "registering") {
          toast.showToast(
            "Processing the scene data to enable auto calibration",
            "success",
          );
        }
      }
    } else if (topic.includes(CONSTANTS.DATA_AUTOCALIB_CAM_POSE)) {
      const id = topic.split("pose/")[1];
      const notification =
        cameraManager.sceneCameras[id].getCalibNotifyElement();
      let span = notification.children[0].querySelectorAll("span")[0];
      if (msg.error === "False") {
        let position = new THREE.Vector3(...msg.translation);
        cameraManager.sceneCameras[id].setPosition(position, true);
        cameraManager.sceneCameras[id].setQuaternion(
          msg.quaternion,
          true,
          true,
        );
        notification.children[0].className =
          notification.children[0].className.replace(
            "alert-default",
            "alert-success",
          );
        span.innerText = "Finished auto camera calibration for " + id;
      } else {
        notification.children[0].className =
          notification.children[0].className.replace(
            "alert-default",
            "alert-danger",
          );
        if (msg.message) {
          span.innerText = msg.message;
        } else {
          span.innerText = "Failed auto camera calibration for " + id;
        }
      }
      notification.children[0].children[1].disabled = false;
      setTimeout(() => {
        notification.remove();
        if (cameraManager.sceneCameras[id])
          cameraManager.sceneCameras[id].enableAutoCalibration(true);
      }, 1000);
    }
  }

  function getMeshToProjectOn() {
    let mesh = scene.getObjectByName("3d_scene");
    if (!mesh) {
      mesh = scene.getObjectByName("floor");
    }
    return mesh;
  }

  function subscribeToTracking() {
    client.subscribe($("#topic").val());
    console.log("Subscribed to " + $("#topic").val());
  }

  function initializeMQTTBroker(brokerField) {
    let host = window.location.hostname;
    let port = window.location.port;
    let broker = brokerField.value;
    let protocol = window.location.protocol;

    // If running HTTPS on a custom port, fix up the WSS connection string
    if (port && protocol === "https:") {
      broker = broker.replace("localhost", host + ":" + port);
    } else {
      // If running HTTPS without a port or HTTP in developer mode, fix up the host name only
      broker = broker.replace("localhost", host);
    }

    // Fix connection string for HTTP in developer mode
    if (protocol === "http:") {
      broker = broker.replace("wss:", "ws:");
      broker = broker.replace("/mqtt", ":1884");
    }

    document.getElementById("broker").value = broker;
  }

  const stats = Stats();
  stats.dom.style = "";
  stats.dom.id = "panel-stats";
  stats.dom.classList.add("stats");
  document.body.appendChild(stats.dom);

  function render() {
    if (resizeRendererToDisplaySize(renderer)) {
      const canvas = renderer.domElement;
      sceneViewCamera.aspect = canvas.clientWidth / canvas.clientHeight;
      sceneViewCamera.updateProjectionMatrix();
    }

    stats.update();
    renderer.render(scene, sceneViewCamera);
    requestAnimationFrame(render);
  }

  render();

  // Set the live view mode when toggle is clicked
  function enableLiveView() {
    // Trigger snapshots for each camera
    document.querySelectorAll(".camera").forEach(function (cam) {
      if (client) {
        client.publish(appName + CONSTANTS.CMD_CAMERA + cam.id, "getimage");
      }
    });
  }

  // Set the camera to 2D orthographic view
  function set2d() {
    let button2d = document.getElementById("2d-button");
    let button3d = document.getElementById("3d-button");

    button2d.classList.add("btn-primary");
    button2d.classList.remove("btn-secondary");
    button3d.classList.add("btn-secondary");
    button3d.classList.remove("btn-primary");

    orbitControls.enabled = false;
    sceneViewCamera = orthographicCamera;
  }

  // Set the camera to 3D perspective view
  function set3d() {
    let button2d = document.getElementById("2d-button");
    let button3d = document.getElementById("3d-button");

    button2d.classList.remove("btn-primary");
    button2d.classList.add("btn-secondary");
    button3d.classList.remove("btn-secondary");
    button3d.classList.add("btn-primary");

    orbitControls.enabled = true;
    sceneViewCamera = perspectiveCamera;
  }

  // Reset the view to the default position (set with controls.saveState())
  function resetView() {
    orbitControls.reset();
  }

  // Handle click event on floor plane toggle
  function updateFloorPlaneVisible(event) {
    let floor = scene.getObjectByName("floor");
    let visible = event.target.checked;

    if (floor) floor["visible"] = visible;
    axesHelper["visible"] = visible;

    // Update local storage
    localStorage.setItem("showFloor", visible);
  }

  document.getElementById("2d-button").addEventListener("click", set2d);
  document.getElementById("3d-button").addEventListener("click", set3d);
  document.getElementById("reset").addEventListener("click", resetView);
  document
    .getElementById("plane-view")
    .addEventListener("change", updateFloorPlaneVisible);
}

main();
