// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import * as THREE from "/static/assets/three.module.js";
import { GLTFLoader } from "/static/examples/jsm/loaders/GLTFLoader.js";
import thingTransformControls from "/static/js/thing/controls/thingtransformcontrols.js";
import validateInputControls from "/static/js/thing/controls/validateinputcontrols.js";
import RESTClient from "/static/js/restclient.js";
import { REST_URL, SUCCESS } from "/static/js/constants.js";

const DEFAULT_FLOOR_WIDTH = 1280;
const DEFAULT_FLOOR_HEIGHT = 720;
const DEFAULT_PPM = 100;
export default class Scene {
  constructor(
    sceneID,
    scene,
    parentFolder,
    perspectiveCamera,
    orthographicCamera,
    renderer,
    toast,
    orbitControls,
    axesHelper,
    isStaff,
  ) {
    let authToken = `Token ${document.getElementById("auth-token").value}`;
    this.restclient = new RESTClient(REST_URL, authToken);

    this.sceneID = sceneID;
    this.scene = scene;
    this.sceneMesh = null;
    this.parentFolder = parentFolder;
    this.renderer = renderer;
    this.orbitControls = orbitControls;
    this.perspectiveCamera = perspectiveCamera;
    this.orthographicCamera = orthographicCamera;
    this.toast = toast;
    this.axesHelper = axesHelper;
    this.isStaff = isStaff;
    this.isParent = false;
    this.updateCamerasOnSave = false;
    this._lastSavedMeshPose = null; // { position: THREE.Vector3, quaternion: THREE.Quaternion }
    Object.assign(this, thingTransformControls);
    Object.assign(this, validateInputControls);
  }

  get transformObject() {
    return this.sceneMesh;
  }

  loadChildAnalytics(sceneThingManagers, thing) {
    const key = thing.concat("s");
    if (this.children) {
      for (const child of this.children) {
        if (key in child) {
          for (const analytic of child[key]) {
            const analyticsParams = sceneThingManagers.things[thing];
            delete analytic.uid;
            analyticsParams.obj.add(analytic);
            analyticsParams.obj.update(0, analyticsParams);
          }
        }
      }
    }
  }

  async loadMap(gltfLoader, loadThings, sceneBoundingBox) {
    let response = await this.restclient.getScene(this.sceneID);
    if (response.statusCode === SUCCESS) {
      this.name = response.content.name;
      this.pixelsPerMeter = response.content.scale;
      let mapis3d = response.content.map
        ? response.content.map.split(".").pop() === "glb"
        : false;
      if (mapis3d) {
        this.load3DMap(
          gltfLoader,
          response.content,
          loadThings,
          sceneBoundingBox,
        );
      } else {
        this.load2DMap(response.content, loadThings, sceneBoundingBox);
      }
      if ("children" in response.content) {
        this.isParent = true;
        this.children = response.content.children;
      }
    }
  }

  computePerspectiveCameraPose(floorWidth, floorHeight) {
    const center = { x: floorWidth / 2, y: floorHeight / 2 };
    let cameraZ =
      floorHeight /
      (2 * Math.tan(THREE.MathUtils.degToRad(this.perspectiveCamera.fov / 2)));
    return { cameraZ, center };
  }

  load3DMap(gltfLoader, sceneDetails, loadThings, sceneBoundingBox) {
    document.getElementById("loader-progress-wrapper").style.display = "flex";
    let progressWrapper = document.getElementById("loader-progress-wrapper");
    let progressBar = progressWrapper.querySelector(".progress-bar");
    let currentProgressClass = "width0";

    gltfLoader.load(
      sceneDetails.map,
      // called when the resource is loaded
      (gltf) => {
        this.sceneMesh = gltf.scene;
        // Position the scene 3D asset based on its configuration
        const settings = {
          rotation: {
            x: sceneDetails.mesh_rotation[0],
            y: sceneDetails.mesh_rotation[1],
            z: sceneDetails.mesh_rotation[2],
          },
          position: {
            x: sceneDetails.mesh_translation[0],
            y: sceneDetails.mesh_translation[1],
            z: sceneDetails.mesh_translation[2],
          },
          scale: {
            x: sceneDetails.mesh_scale[0],
            y: sceneDetails.mesh_scale[1],
            z: sceneDetails.mesh_scale[2],
          },
        };

        for (const setting in settings) {
          for (const axis in settings[setting]) {
            if (
              settings[setting][axis] != null &&
              settings[setting][axis] !== ""
            ) {
              if (setting === "rotation")
                this.sceneMesh[setting][axis] = THREE.MathUtils.degToRad(
                  settings[setting][axis],
                );
              else this.sceneMesh[setting][axis] = settings[setting][axis];
            }
          }
        }

        this.sceneMesh.name = "3d_scene";
        this.sceneMesh.castShadow = true;
        this.scene.add(this.sceneMesh);
        // Cache the initial saved mesh pose
        this._lastSavedMeshPose = {
          position: this.sceneMesh
            .getWorldPosition(new THREE.Vector3())
            .clone(),
          quaternion: this.sceneMesh
            .getWorldQuaternion(new THREE.Quaternion())
            .clone(),
        };
        this.addControlPanel(true);
        this.addDragControls(this.perspectiveCamera, this.orbitControls);
        sceneBoundingBox.setFromObject(this.sceneMesh);
        const size = new THREE.Vector3();
        sceneBoundingBox.getSize(size);

        let floorWidth = size.x;
        let floorHeight = size.z;
        var { cameraZ, center } = this.computePerspectiveCameraPose(
          floorWidth,
          floorHeight,
        );

        this.initializeScene(cameraZ, center, floorHeight, floorWidth);

        loadThings();

        document.getElementById("loader-progress-wrapper").style.display =
          "none";
      },
      // called while loading is progressing
      (xhr) => {
        let percentBy5 = parseInt((xhr.loaded / xhr.total) * 20) * 5;
        let percent = parseInt((xhr.loaded / xhr.total) * 100);

        progressBar.classList.remove(currentProgressClass);
        currentProgressClass = "width" + percentBy5;
        progressBar.classList.add(currentProgressClass);
        progressBar.setAttribute("aria-valuenow", percent);
        progressBar.innerText = "Scene: " + percent + "%";
      },
      // called when loading has errors
      (error) => {
        console.log("Error loading glTF: " + error);
      },
    );
  }

  load2DMap(sceneDetails, loadThings, sceneBoundingBox) {
    let loader = new THREE.TextureLoader();
    if (sceneDetails.map) {
      loader.load(sceneDetails.map, (tex) => {
        let floorWidth = tex.image.width / this.pixelsPerMeter;
        let floorHeight = tex.image.height / this.pixelsPerMeter;
        var { cameraZ, center } = this.computePerspectiveCameraPose(
          floorWidth,
          floorHeight,
        );

        // Create the scene floor using a PlaneGeometry
        // The size in meters is based on the scale as defined by the user and the image size
        const floorGeometry = new THREE.PlaneGeometry(floorWidth, floorHeight);
        const floorMaterial = new THREE.MeshLambertMaterial({
          map: tex,
          opacity: 0.8,
          transparent: true,
        });

        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        this.floorMesh = floor;
        floor.name = "floor";

        // Set the origin to the bottom left corner of the scene
        floor.position.set(center.x, center.y, 0);
        sceneBoundingBox.setFromObject(floor);

        // Set the perspective camera position.z based on the scene size and camera FOV
        this.initializeScene(cameraZ, center, floorHeight, floorWidth);
        loadThings();
        this.addControlPanel();

        floor["visible"] = this.axesHelper["visible"] =
          this.initFloorPlaneVisible();
        this.scene.add(floor);
      });
    } else {
      let floorWidth =
        DEFAULT_FLOOR_WIDTH /
        (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
      let floorHeight =
        DEFAULT_FLOOR_HEIGHT /
        (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
      var { cameraZ, center } = this.computePerspectiveCameraPose(
        floorWidth,
        floorHeight,
      );

      // Set the perspective camera position.z based on the scene size and camera FOV
      this.initializeScene(cameraZ, center, floorHeight, floorWidth);
      loadThings();
      this.addControlPanel();

      this.axesHelper["visible"] = this.initFloorPlaneVisible();
    }
  }

  // ── Map source ───────────────────────────────────────────────────────
  // Each source (user upload, handheld SLAM, world model) contributes one
  // current mesh; a new upload from a source replaces its previous one. The
  // dropdown previews a source's mesh; "set as default" makes it Scene.map.
  // Nothing is persisted on selection alone.
  async addMapSourceControls() {
    const response = await this.restclient.getSourceMaps(this.sceneID);
    if (response.statusCode !== SUCCESS) return;
    const { maps, default: defaultMethod } = response.content;
    if (!maps?.some((map) => map.method !== defaultMethod)) return;

    this._sourceMaps = {};
    const labels = defaultMethod === null ? { "Current map ✓": null } : {};
    for (const map of maps) {
      const when = map.created
        ? map.created.replace("T", " ").slice(0, 16)
        : "";
      const who = map.contributor ? ` · ${map.contributor}` : "";
      const tag = map.method === defaultMethod ? " ✓" : "";
      const label = `${map.method}${who} · ${when}${tag}`;
      labels[label] = map.method;
      this._sourceMaps[map.method] = map;
    }
    this._defaultMethod = defaultMethod;
    this._previewMethod = defaultMethod;

    const current =
      Object.keys(labels).find((k) => labels[k] === defaultMethod) ||
      Object.keys(labels)[0];
    const settings = { "map source": current };
    this._mapSourceSettings = settings;
    this._sourceMapLabels = Object.fromEntries(
      Object.entries(labels).map(([label, method]) => [method, label]),
    );
    this.mapSourceFolder = this.controlsFolder.addFolder("Map Source");
    this._mapSourceController = this.mapSourceFolder
      .add(settings, "map source", Object.keys(labels))
      .onChange((label) => this.previewSourceMap(labels[label]));
    this._mapSourceController.$widget.id = "map-source-select";

    if (this.isStaff !== null) {
      const actions = {
        "set as default": () => this.activateSourceMap(this._previewMethod),
        "delete source map": () => this.deleteSourceMap(this._previewMethod),
      };
      this.mapSourceFolder.add(actions, "set as default").$widget.id =
        "map-source-activate";
      this.mapSourceFolder.add(actions, "delete source map").$widget.id =
        "map-source-delete";
    }
  }

  previewSourceMap(method) {
    if (method === this._defaultMethod) {
      this._previewRequestId = (this._previewRequestId || 0) + 1;
      this._previewLoading = false;
      this.clearMapPreview();
      this._previewMethod = method;
      this.setMapPreviewReadOnly(false);
      this.updateMapSourceSelection();
      const progress = document.getElementById("loader-progress-wrapper");
      if (progress) progress.style.display = "none";
      return;
    }
    const map = this._sourceMaps && this._sourceMaps[method];
    if (!map || !map.file) return;
    const requestId = (this._previewRequestId =
      (this._previewRequestId || 0) + 1);
    this._previewLoading = true;
    this.setMapPreviewReadOnly(true);
    // Same progress bar the page shows on first load; a multi-MB GLB can
    // take seconds and the view must not look frozen meanwhile.
    const wrapper = document.getElementById("loader-progress-wrapper");
    const bar = wrapper ? wrapper.querySelector(".progress-bar") : null;
    let widthClass = "width0";
    const showProgress = (percent) => {
      if (!wrapper || !bar) return;
      wrapper.style.display = "flex";
      const by5 = Math.min(100, Math.floor(percent / 5) * 5);
      bar.classList.remove(widthClass);
      widthClass = "width" + by5;
      bar.classList.add(widthClass);
      bar.setAttribute("aria-valuenow", percent);
      bar.innerText = `${method}: ${percent}%`;
    };
    const hideProgress = () => {
      if (wrapper) wrapper.style.display = "none";
    };
    showProgress(0);
    const loader = new GLTFLoader();
    loader.load(
      map.file,
      (gltf) => {
        if (requestId !== this._previewRequestId) {
          this.disposePreviewMesh(gltf.scene);
          return;
        }
        hideProgress();
        const t = map.transform || {};
        const rot = t.rotation || [0, 0, 0];
        const pos = t.translation || [0, 0, 0];
        const scl = t.scale || [1, 1, 1];
        gltf.scene.rotation.set(
          THREE.MathUtils.degToRad(rot[0]),
          THREE.MathUtils.degToRad(rot[1]),
          THREE.MathUtils.degToRad(rot[2]),
        );
        gltf.scene.position.set(pos[0], pos[1], pos[2]);
        gltf.scene.scale.set(scl[0], scl[1], scl[2]);
        gltf.scene.name = "3d_scene";
        gltf.scene.castShadow = true;
        this.clearMapPreview();
        this._previewMesh = gltf.scene;
        this.scene.add(this._previewMesh);
        const activeMap = this.sceneMesh || this.floorMesh;
        if (activeMap) activeMap.visible = false;
        this._previewMethod = method;
        this._previewLoading = false;
        this.updateMapSourceSelection();
        this.toast.showToast(
          method === this._defaultMethod
            ? `Showing default map (${method})`
            : `Previewing ${method} map — not the default`,
          "info",
        );
      },
      (xhr) => {
        if (requestId === this._previewRequestId && xhr.total) {
          showProgress(Math.round((xhr.loaded / xhr.total) * 100));
        }
      },
      (error) => {
        if (requestId !== this._previewRequestId) return;
        hideProgress();
        this._previewLoading = false;
        this.setMapPreviewReadOnly(Boolean(this._previewMesh));
        this.updateMapSourceSelection();
        console.log("Error loading source map glTF: " + error);
        this.toast.showToast("Could not load that source's map", "error");
      },
    );
  }

  updateMapSourceSelection() {
    if (!this._mapSourceSettings) return;
    this._mapSourceSettings["map source"] =
      this._sourceMapLabels[this._previewMethod];
    this._mapSourceController.updateDisplay();
  }

  setMapPreviewReadOnly(readOnly) {
    if (readOnly && !this._previewEditState) {
      const editable = new Set([
        "save",
        "name",
        "pixels per meter",
        "Update Cameras",
        "toggle rotate/translate",
        "pos X",
        "pos Y",
        "pos Z",
        "rot X",
        "rot Y",
        "rot Z",
      ]);
      const controls = this.controlsFolder
        .controllersRecursive()
        .filter((control) => editable.has(control.property))
        .map((control) => ({
          control,
          disabled: control._disabled,
        }));
      const cameras = this._getAllSceneCameraWrappers().map((camera) => ({
        camera,
        projectFrame: camera.projectFrame,
        meshVisible: camera.mesh?.visible,
        captureVisible: camera.cameraCapture?.visible,
        frameControlDisabled:
          camera.controllersDict?.["project frame"]?._disabled,
      }));
      this._previewEditState = {
        controls,
        cameras,
        meshVisible: this.sceneMesh?.visible,
        floorVisible: this.floorMesh?.visible,
        transformEnabled: this.transformControl?.enabled,
        transformVisible: this.transformControl
          ? this.getTransformControlObject3D().visible
          : false,
      };
      for (const { control } of controls) control.disable();
      for (const { camera } of cameras) {
        camera.projectFrame = false;
        if (camera.mesh) camera.mesh.visible = false;
        if (camera.cameraCapture) camera.cameraCapture.visible = false;
        camera.controllersDict?.["project frame"]?.disable();
      }
      if (this.transformControl) {
        this.transformControl.enabled = false;
        this.transformControl.detach();
        this.setTransformControlVisibility(false);
      }
    } else if (!readOnly && this._previewEditState) {
      const state = this._previewEditState;
      if (this.sceneMesh) this.sceneMesh.visible = state.meshVisible;
      if (this.floorMesh) this.floorMesh.visible = state.floorVisible;
      for (const { control, disabled } of state.controls)
        control.disable(disabled);
      for (const {
        camera,
        projectFrame,
        meshVisible,
        captureVisible,
        frameControlDisabled,
      } of state.cameras) {
        camera.projectFrame = projectFrame;
        if (camera.mesh) camera.mesh.visible = meshVisible;
        if (camera.cameraCapture) camera.cameraCapture.visible = captureVisible;
        camera.controllersDict?.["project frame"]?.disable(
          Boolean(frameControlDisabled),
        );
      }
      if (this.transformControl) {
        if (this.sceneMesh) this.transformControl.attach(this.sceneMesh);
        this.transformControl.enabled = state.transformEnabled;
        this.setTransformControlVisibility(state.transformVisible);
      }
      this._previewEditState = null;
    }
  }

  clearMapPreview() {
    if (!this._previewMesh) return;
    this.scene.remove(this._previewMesh);
    this.disposePreviewMesh(this._previewMesh);
    this._previewMesh = null;
  }

  disposePreviewMesh(mesh) {
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();
    mesh.traverse((object) => {
      if (object.geometry) geometries.add(object.geometry);
      for (const material of Array.isArray(object.material)
        ? object.material
        : [object.material]) {
        if (!material) continue;
        materials.add(material);
        for (const value of Object.values(material)) {
          if (value?.isTexture) textures.add(value);
        }
      }
    });
    for (const resource of [...textures, ...materials, ...geometries])
      resource.dispose();
  }

  async activateSourceMap(method) {
    if (this._previewLoading || method !== this._previewMethod) return;
    if (!method || method === this._defaultMethod) return;
    const response = await this.restclient.activateSourceMap(
      this.sceneID,
      method,
    );
    if (response.statusCode === SUCCESS) {
      this.toast.showToast("Default map updated — reloading", "success");
      setTimeout(() => window.location.reload(), 800);
    } else {
      const detail =
        (response.content &&
          (response.content.error || response.content.detail)) ||
        "";
      this.toast.showToast(`Could not set default map. ${detail}`, "error");
    }
  }

  async deleteSourceMap(method) {
    if (this._previewLoading) return;
    if (!method || method === this._defaultMethod) {
      this.toast.showToast("The default map cannot be deleted", "warning");
      return;
    }
    if (!window.confirm("Delete this source's map?")) return;
    const response = await this.restclient.deleteSourceMap(
      this.sceneID,
      method,
    );
    if (response.statusCode === 204) {
      this.toast.showToast("Source map deleted — reloading", "success");
      setTimeout(() => window.location.reload(), 800);
    } else {
      const detail =
        (response.content &&
          (response.content.error || response.content.detail)) ||
        "";
      this.toast.showToast(`Could not delete source map. ${detail}`, "error");
    }
  }

  initializeScene(cameraZ, center, floorHeight, floorWidth) {
    this.perspectiveCamera.position.set(center.x, center.y, cameraZ);

    // Calculate the delta between the canvas width and the floor width
    let delta = (floorHeight * this.perspectiveCamera.aspect - floorWidth) / 2;

    // Set up the orthographic camera to match the canvas size and centered on the floor
    this.orthographicCamera.left = -delta;
    this.orthographicCamera.right =
      floorHeight * this.perspectiveCamera.aspect - delta;
    this.orthographicCamera.top = floorHeight;
    this.orthographicCamera.bottom = 0;
    this.orthographicCamera.position.set(0, 0, cameraZ);
    this.orthographicCamera.updateProjectionMatrix();

    // Directional scene lighting - matching Open3D sun light setup
    // Check if a directional light already exists and update it, otherwise add a new one
    let directionalLight = this.scene.getObjectByName("directionalLight");
    if (!directionalLight) {
      directionalLight = new THREE.DirectionalLight(0xffffff, 1.0);
      directionalLight.name = "directionalLight";
      this.scene.add(directionalLight);
    }
    // Match Open3D sun light: direction [0.0, 0.0, -1.0] pointing straight down
    // In Three.js, light points FROM position TO origin, so we set position to [0, 0, 1]
    directionalLight.position.set(0, 0, 1);

    // Center orbit controls on the scene
    this.orbitControls.target.set(center.x, center.y, 1);

    // Save this as the initial view
    this.orbitControls.saveState();
    // Initial reset (sometimes the scene loads rotated otherwise)
    this.orbitControls.reset();
  }

  // Initialize the floor plane visibility
  initFloorPlaneVisible() {
    // Browser only stores string, JSON.parse restores boolean value
    let showFloor = JSON.parse(localStorage.getItem("showFloor"));
    let checkbox = document.getElementById("plane-view");

    // Check if showFloor is in local storage yet
    if (showFloor === null) {
      if (checkbox.checked) {
        localStorage.setItem("showFloor", true);
        showFloor = true;
      } else {
        localStorage.setItem("showFloor", false);
        showFloor = false;
      }
    } else {
      // Set checkbox to the value from local storage
      checkbox.checked = showFloor;
    }

    return showFloor;
  }

  addControlPanel(isMesh = false) {
    let panelSettings = {
      name: this.name,
      "pixels per meter":
        this.pixelsPerMeter != null ? this.pixelsPerMeter : "",
    };

    this.controlsFolder = this.parentFolder.addFolder("Scene Settings");
    let control = this.controlsFolder.add(panelSettings, "name").onChange(
      function (value) {
        this.name = value;
        this.validateField("name", () => {
          return this.name === "";
        });
      }.bind(this),
    );

    control = this.controlsFolder
      .add(panelSettings, "pixels per meter")
      .onChange(
        function (value) {
          this.pixelsPerMeter = value;
          this.validateField("pixels per meter", () => {
            return this.pixelsPerMeter === "";
          });
        }.bind(this),
      );

    if (isMesh) {
      this.addPoseControls(panelSettings);
      this.controlsFolder.$title.addEventListener(
        "click",
        ((event) => {
          this.toggleTransformControl();
        }).bind(this),
      );
      // Add checkbox to keep camera relative pose on save
      panelSettings = Object.assign(panelSettings, {
        "Update Cameras": this.updateCamerasOnSave,
      });
      this.controlsFolder.add(panelSettings, "Update Cameras").onChange(
        function (value) {
          this.updateCamerasOnSave = value;
        }.bind(this),
      );
    }
    this.addMapSourceControls();

    if (this.isStaff === null) {
      for (const field of Object.keys(panelSettings)) {
        this.executeOnControl(field, (control) => {
          control[0].disable(true);
        });
      }
    } else {
      if (document.getElementById("scene-qr-data")) {
        panelSettings["scene QR code"] = () => {
          document.dispatchEvent(new Event("scene-qr-open"));
        };
        this.controlsFolder.add(panelSettings, "scene QR code");
      }
      panelSettings = Object.assign(panelSettings, {
        save: function () {
          this.saveSettings();
        }.bind(this),
      });
      control = this.controlsFolder.add(panelSettings, "save");
      this.executeOnControl("save", (control) => control[0].disable(true));
    }

    this.controlsFolder.close();
  }

  updateSaveButton() {
    if (this.isStaff === null || this._previewLoading || this._previewMesh)
      return;
    this.executeOnControl("save", (control) => control[0].disable(false));
  }

  async saveSettings() {
    if (this._previewLoading || this._previewMesh) {
      this.toast.showToast(
        "Return to the default map before editing scene settings",
        "warning",
      );
      return;
    }
    let sceneData = {
      name: this.name,
      scale: this.pixelsPerMeter,
    };

    if (this.transformObject !== null) {
      let sceneMesh = this.transformObject.clone();

      sceneData = Object.assign({}, sceneData, {
        mesh_translation: [...sceneMesh.position],
        mesh_rotation: [
          sceneMesh.rotation.x,
          sceneMesh.rotation.y,
          sceneMesh.rotation.z,
        ].map(function (item) {
          return THREE.MathUtils.radToDeg(item);
        }),
      });
    }
    // If enabled, maintain camera poses relative to mesh and persist cameras
    if (this.updateCamerasOnSave && this.sceneMesh) {
      try {
        await this._applyMeshDeltaToCamerasAndSave();
      } catch (e) {
        console.error("Failed to update cameras relative to mesh:", e);
      }
    }

    this.updateScene(sceneData);
    this.executeOnControl("save", (control) => control[0].disable(true));
  }

  async updateScene(sceneData) {
    let updateResponse = await this.restclient.updateScene(
      this.sceneID,
      sceneData,
      { timeout: 10000 },
    );
    if (updateResponse.statusCode === SUCCESS) {
      this.toast.showToast("Scene mesh settings have been updated!", "success");
      // On successful save, refresh cached mesh pose
      if (this.sceneMesh) {
        this._lastSavedMeshPose = {
          position: this.sceneMesh
            .getWorldPosition(new THREE.Vector3())
            .clone(),
          quaternion: this.sceneMesh
            .getWorldQuaternion(new THREE.Quaternion())
            .clone(),
        };
      }
      this.updateSceneObjects();
    } else {
      console.log(updateResponse.errors);
      this.toast.showToast(
        "Something went wrong. Failed to update scene mesh settings. Please try again!",
        "danger",
      );
    }
  }

  updateSceneObjects() {
    // Update the scale and position of the scene objects based on the new pixels per meter value
    if (this.sceneMesh) {
      const size = new THREE.Vector3();
      const sceneBoundingBox = new THREE.Box3().setFromObject(this.sceneMesh);
      sceneBoundingBox.getSize(size);
      let floorWidth = size.x;
      let floorHeight = size.z;
      var { cameraZ, center } = this.computePerspectiveCameraPose(
        floorWidth,
        floorHeight,
      );
      this.initializeScene(cameraZ, center, floorHeight, floorWidth);
    } else {
      // Handle 2D map case
      let floorWidth =
        DEFAULT_FLOOR_WIDTH /
        (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
      let floorHeight =
        DEFAULT_FLOOR_HEIGHT /
        (this.pixelsPerMeter != null ? this.pixelsPerMeter : DEFAULT_PPM);
      var { cameraZ, center } = this.computePerspectiveCameraPose(
        floorWidth,
        floorHeight,
      );
      this.initializeScene(cameraZ, center, floorHeight, floorWidth);
    }
  }

  // Helper: find all SceneCamera wrappers in the THREE scene graph
  _getAllSceneCameraWrappers() {
    let cameras = [];
    this.scene.traverse((obj) => {
      if (obj && obj.sceneCamera) {
        cameras.push(obj);
      }
    });
    return cameras;
  }

  // Apply mesh delta transform to each camera's sceneCamera and save to backend
  async _applyMeshDeltaToCamerasAndSave() {
    if (!this._lastSavedMeshPose || !this.sceneMesh) return;

    // Compute delta = newMesh * inverse(oldMesh)
    const oldMatrix = new THREE.Matrix4().compose(
      this._lastSavedMeshPose.position.clone(),
      this._lastSavedMeshPose.quaternion.clone(),
      new THREE.Vector3(1, 1, 1),
    );
    const newPos = this.sceneMesh.getWorldPosition(new THREE.Vector3());
    const newQuat = this.sceneMesh.getWorldQuaternion(new THREE.Quaternion());
    const newMatrix = new THREE.Matrix4().compose(
      newPos,
      newQuat,
      new THREE.Vector3(1, 1, 1),
    );
    const invOld = new THREE.Matrix4().copy(oldMatrix).invert();
    const delta = new THREE.Matrix4().multiplyMatrices(newMatrix, invOld);

    const cameraWrappers = this._getAllSceneCameraWrappers();
    for (const camWrapper of cameraWrappers) {
      const camObj = camWrapper.sceneCamera; // THREE.PerspectiveCamera
      // Apply delta in world space. If wrapper has identity transform (default), this is safe.
      camObj.applyMatrix4(delta);
      camWrapper.setPoseSuffix && camWrapper.setPoseSuffix();
      camWrapper.updateSaveButton && camWrapper.updateSaveButton();
    }

    // Persist each camera to backend
    for (const camWrapper of cameraWrappers) {
      if (camWrapper.saveSettings) {
        try {
          // saveSettings already handles y-up/down conversion and backend update
          // Await sequentially to avoid flooding backend
          // eslint-disable-next-line no-await-in-loop
          await camWrapper.saveSettings();
        } catch (e) {
          console.error("Failed to save camera:", camWrapper.name, e);
        }
      }
    }
  }
}
