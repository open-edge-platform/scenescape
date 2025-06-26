// SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

/**
 * @module viewport
 * @description This module provides general functions for creating a 3D viewport using Three.js.
 */

'use strict';

import * as THREE from '/static/assets/three.module.js';
import { OrbitControls } from '/static/examples/jsm/controls/OrbitControls.js';
import {
  CALIBRATION_POINT_COLORS,
  CALIBRATION_SCALE_FACTOR,
  CALIBRATION_TEXT_SIZE,
  CAMERA_FOV,
  CAMERA_ASPECT,
  CAMERA_NEAR,
  CAMERA_FAR,
  MAX_CALIBRATION_POINTS,
  SCENE_MAX_TEXTURE_SIZE,
  SPHERE_RADIUS,
  REST_URL
} from '/static/js/constants.js';
import { Draw } from '/static/js/draw.js';
import { isMeshToProjectOn } from '/static/js/interactions.js';
import RESTClient from '/static/js/restclient.js';

const TEXT_POSITION = new THREE.Vector3(SPHERE_RADIUS, SPHERE_RADIUS, 0);

class Viewport extends THREE.Scene {
  constructor(canvas, scale, sceneID, authToken, gltfLoader, renderer) {
    super();
    this.sceneID = sceneID;
    this.sceneMesh = null;
    this.floorWidth = null;
    this.floorHeight = null;
    this.sceneScale = scale;
    this.restClient = new RESTClient(REST_URL, authToken);
    this.canvas = canvas;
    this.gltfLoader = gltfLoader;
    this.renderer = renderer;
    this.raycaster = new THREE.Raycaster();
    this.textureLoader = new THREE.TextureLoader();

    this.isDragging = false;
    this.calibrationUpdated = false;
    this.draggingPoint = null;

    this.projectedMaterial = null;
    this.mesh = null;

    this.scaleFactor = 1.0;
    this.sceneBoundingBox = new THREE.Box3();
    this.drawObject = new Draw();
    this.calibrationPointNames = [];

    for (let i = 0; i < MAX_CALIBRATION_POINTS; i++) {
      this.calibrationPointNames.push(`p${i}`);
    }

    // Set the default up vector for the viewport
    THREE.Object3D.DEFAULT_UP = new THREE.Vector3(0, 0, 1);

    // Ambient scene lighting and background
    this.background = new THREE.Color(0x808080);
    const ambientColor = 0x707070; // Soft white
    const ambientLight = new THREE.AmbientLight(ambientColor);
    this.add(ambientLight);

    // Set the cameras
    this.perspectiveCamera = new THREE.PerspectiveCamera(
      CAMERA_FOV, CAMERA_ASPECT, CAMERA_NEAR, CAMERA_FAR);
    this.projectionCamera = this.perspectiveCamera.clone();
    this.add(this.perspectiveCamera)
    this.add(this.projectionCamera);

    this.orbitControls = new OrbitControls(this.perspectiveCamera, renderer.domElement);
    this.orbitControls.enableDamping = true; // Enable damping (inertia)
    this.orbitControls.dampingFactor = 0.25; // Damping factor
    this.orbitControls.screenSpacePanning = true; // Enable panning in screen space
    this.orbitControls.minDistance = 1; // Minimum zoom distance
    this.orbitControls.maxDistance = 2000; // Maximum zoom distance
    this.orbitControls.maxPolarAngle = Math.PI / 2; // Limit vertical rotation
  }

  #getCanvasDiagonal() {
    return Math.sqrt(this.canvas.width ** 2 + this.canvas.height ** 2);
  }

  #updateObjectScale(object, scaleFactor) {
    const distance = this.perspectiveCamera.position.distanceTo(object.position);
    const scale = distance / scaleFactor;
    object.scale.set(scale, scale, scale);
  }

  // Calibration point handling function derived from interactions.js
  // TODO: eventual goal is to unify the two sets of functions but will need to refactor
  // the interactions.js functions to not depend on interactions with a camera object.

  initializeEventListeners() {
    this.canvas.addEventListener("mousedown", (event) => this.onMouseDown(event));
    this.canvas.addEventListener("mousemove", (event) => this.onMouseMove(event));
    this.canvas.addEventListener("mouseup", (event) => this.onMouseUp(event));
    this.canvas.addEventListener("wheel", () => this.updateCalibrationPointScale(), { passive: true });
    this.canvas.addEventListener("dblclick", (event) => this.onDoubleClick(event));
    this.canvas.addEventListener("contextmenu", (event) => this.onRightClick(event));
  }

  // Disable orbit controls and check if a calibration point is clicked
  onMouseDown(event) {
    let mouse = {
      x: (event.offsetX / this.renderer.domElement.clientWidth) * 2 - 1,
      y: -(event.offsetY / this.renderer.domElement.clientHeight) * 2 + 1,
    }

    this.raycaster.setFromCamera(mouse, this.perspectiveCamera);

    const intersects = this.raycaster.intersectObjects(this.children, true);
    for (const intersect of intersects) {
      if (intersect.object.name.startsWith("calibrationPoint_")) {
        this.isDragging = true;
        this.draggingPoint = intersect.object;
        this.orbitControls.enabled = false;
        return;
      }
    }
  }

  onMouseMove(event) {
    if (this.isDragging) {
      let mouse = {
        x: (event.offsetX / this.renderer.domElement.clientWidth) * 2 - 1,
        y: -(event.offsetY / this.renderer.domElement.clientHeight) * 2 + 1,
      }

      this.raycaster.setFromCamera(mouse, this.perspectiveCamera);

      const intersects = this.raycaster.intersectObjects(this.children, true);
      for (const intersect of intersects) {
        if (isMeshToProjectOn(intersect)) {
          this.draggingPoint.position.copy(intersect.point);
          this.calibrationUpdated = true;
          return;
        }
      }
    }
  }

  onMouseUp(event) {
    // Prevent context menu from appearing in edge browser
    event.preventDefault();

    this.isDragging = false;
    this.draggingPoint = null;
    this.orbitControls.enabled = true;
  }

  onDoubleClick(event) {
    event.preventDefault();
    let mouse = {
      x: (event.offsetX / this.renderer.domElement.clientWidth) * 2 - 1,
      y: -(event.offsetY / this.renderer.domElement.clientHeight) * 2 + 1,
    }

    this.raycaster.setFromCamera(mouse, this.perspectiveCamera);

    const intersects = this.raycaster.intersectObjects(this.children, true);
    for (const intersect of intersects) {
      if (isMeshToProjectOn(intersect)) {
        const { x, y, z } = intersect.point;
        this.addCalibrationPoint(x, y, z);
        return;
      }
    }
  }

  onRightClick(event) {
    event.preventDefault();

    let mouse = {
      x: (event.offsetX / this.renderer.domElement.clientWidth) * 2 - 1,
      y: -(event.offsetY / this.renderer.domElement.clientHeight) * 2 + 1,
    }
    this.raycaster.setFromCamera(mouse, this.perspectiveCamera);

    const intersects = this.raycaster.intersectObjects(this.children, true);
    for (const intersect of intersects) {
      if (intersect.object.name.startsWith("calibrationPoint_")) {
        const objectHit = intersect.object;
        this.remove(objectHit);
        this.calibrationPointNames.push(objectHit.name.split("_")[1]);
        this.calibrationPointNames.sort((a, b) => {
          const numA = parseInt(a.replace(/\D/g, ""));
          const numB = parseInt(b.replace(/\D/g, ""));
          return numA - numB;
        });
        return;
      }
    }
  }

  resetCameraView() {
    this.initializeCamera();
    this.orbitControls.target.set(this.floorWidth / 2, this.floorHeight / 2, 1);
  }

  addCalibrationPoint(x, y, z) {
    const name = this.calibrationPointNames.shift();
    const point = {x: x, y: y, z: z};
    // Extract integer from name to determine color
    const number = parseInt(name.replace(/\D/g, ""));
    const color = CALIBRATION_POINT_COLORS[number % CALIBRATION_POINT_COLORS.length];
    const pointMesh = this.drawObject.createCalibrationPoint(name, point, color);
    // Scale the point on creation to an appropriate size based on the canvas dimensions
    const scaleFactor = this.#getCanvasDiagonal() / CALIBRATION_SCALE_FACTOR;
    this.#updateObjectScale(pointMesh, scaleFactor);
    this.add(pointMesh);
    this.calibrationUpdated = true;

    this.drawObject.createTextObject(name, TEXT_POSITION, CALIBRATION_TEXT_SIZE)
      .then((textMesh) => {
        pointMesh.add(textMesh);
      })
      .catch((error) => {
        console.error("Error adding text to calibration point:", error);
      });
  }

  updateCalibrationPointScale() {
    const scaleFactor = this.#getCanvasDiagonal() / CALIBRATION_SCALE_FACTOR;

    this.children
      .filter((child) => child.name.startsWith("calibrationPoint_"))
      .forEach((child) => this.#updateObjectScale(child, scaleFactor));
  }

  clearCalibrationPoints() {
    this.children
      .filter((child) => child.name.startsWith("calibrationPoint_"))
      .forEach((child) => this.remove(child));

    this.calibrationPointNames = [];
    for (let i = 0; i < MAX_CALIBRATION_POINTS; i++) {
      this.calibrationPointNames.push(`p${i}`);
    }
  }

  getCalibrationPointCount() {
    return this.children.filter((child) => child.name.startsWith("calibrationPoint_")).length;
  }

  // Get the world coordinates of all calibration points
  getCalibrationPoints(scaled = false) {
    return this.children
      .filter(child => child.name.startsWith("calibrationPoint_"))
      .map(child => {
        const position = child.position.clone();
        if (scaled) {
          position.multiplyScalar(this.sceneScale * this.scaleFactor);
        }
        const name = child.name.replace("calibrationPoint_", "");
        return { name, position: [position.x, position.y, position.z] };
      })
      .sort((a, b) => {
        const numA = parseInt(a.name.replace(/\D/g, ""));
        const numB = parseInt(b.name.replace(/\D/g, ""));
        return numA - numB;
      })
      .reduce((acc, point) => {
        acc[point.name] = point.position;
        return acc;
      }, {});
  }

  // Camera image projection functions

  setCameraPose(matrix) {
    const euler = new THREE.Euler();
    euler.setFromRotationMatrix(matrix);
    const position = new THREE.Vector3();
    position.setFromMatrixPosition(matrix);
    this.projectionCamera.rotation.copy(euler);
    this.projectionCamera.position.copy(position);
    // Re-enable the projection if it has been disabled by clearing calibration points
  }

  projectImage(image, cameraMtx) {
    if (this.sceneMesh !== null) {
      this.textureLoader.load(image, (texture) => {
        this.projectionCamera.aspect = texture.image.width / texture.image.height;
        this.projectionCamera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(texture.image.height / (2 * cameraMtx[1][1])));
        this.projectionCamera.updateProjectionMatrix();
        if (this.projectedMaterial === null) {
          [ this.projectedMaterial, this.mesh ] = this.drawObject.createProjectionMaterial(this.projectionCamera, this.sceneMesh, texture);
          this.projectedMaterial.opacity = this.initialOpacity;
          this.add(this.mesh);
        } else {
          this.projectedMaterial.texture = texture;
          this.projectedMaterial.project(this.mesh);
        }
        this.setProjectionVisibility(true);
      });
    }
  }

  setProjectionVisibility(visibility) {
    if (this.projectedMaterial) {
      this.projectedMaterial.visible = visibility;
    }
  }

  setProjectionOpacity(opacity) {
    if (this.projectedMaterial) {
      this.projectedMaterial.opacity = opacity;
    } else {
      this.initialOpacity = opacity;
    }
  }

  // Scene map loading functions

  computePerspectiveCameraPose(floorWidth, floorHeight, fov) {
    const center = { x: floorWidth / 2, y: floorHeight / 2 };
    const cameraZ = floorHeight / (2 * Math.tan(THREE.MathUtils.degToRad(fov / 2)));
    return { cameraZ, center };
  }

  resizeImage(image, maxWidth, maxHeight) {
    return new Promise((resolve) => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      let width = image.width;
      let height = image.height;
      this.scaleFactor = 1;

      canvas.width = width;
      canvas.height = height;
      ctx.drawImage(image, 0, 0, width, height);

      resolve(canvas);
    });
  }

  loadMap() {
    return new Promise((resolve, reject) => {
      this.restClient.getScene(this.sceneID).then((response) => {
        if (response.statusCode === 200) {
          this.name = response.content.name;
          const map = response.content.map;
          if (map) {
            if (map.split('.').pop() === 'glb') {
              this.load3DMap(
                map,
                response.content.mesh_rotation,
                response.content.mesh_translation,
                response.content.mesh_scale
              ).then(resolve).catch(reject);
            } else {
              this.load2DMap(map).then(resolve).catch(reject);
            }
          }
        } else {
          reject(response.content);
        }
      })
      .catch((error) => {
        console.error("Error retrieving scene info:", error);
        reject(error);
      });
    });
  }

  load2DMap(map) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.src = map;

      image.onload = () => {
        this.resizeImage(image, SCENE_MAX_TEXTURE_SIZE, SCENE_MAX_TEXTURE_SIZE).then((canvas) => {
          const texture = new THREE.Texture(canvas);
          texture.needsUpdate = true;

          console.log("Loaded and resized 2D map:", image.src);
          this.floorWidth = canvas.width / this.sceneScale;
          this.floorHeight = canvas.height / this.sceneScale;
          const floorGeometry = new THREE.PlaneGeometry(this.floorWidth, this.floorHeight);
          const floorMaterial = new THREE.MeshBasicMaterial({
            map: texture,
            opacity: 1,
            transparent: true,
          });
          const floor = new THREE.Mesh(floorGeometry, floorMaterial);
          floor.name = "floor";
          floor.position.set(this.floorWidth / 2, this.floorHeight / 2, 0);
          this.sceneBoundingBox.setFromObject(floor);
          floor.visible = true;
          this.sceneMesh = floor;
          this.add(floor);

          resolve();
        }).catch((error) => {
          console.error("Error resizing image:", error);
          reject(error);
        });
      };

      image.onerror = (error) => {
        console.error("Error loading 2D map:", error);
        reject(error);
      };
    });
  }

  load3DMap(map, rotation, translation, scale) {
    return new Promise((resolve, reject) => {
      $("#loader-progress-wrapper").css("display", "flex");
      const progressBar = $("#loader-progress-wrapper").find(".progress-bar");
      let currentProgressClass = "width0";

      this.gltfLoader.load(
        map,
        // called when the resource is loaded
        (gltf) => {
          this.sceneMesh = gltf.scene;
          // Position the scene 3D asset based on its configuration
          const settings = {
            'rotation': {
              'x': rotation[0],
              'y': rotation[1],
              'z': rotation[2]
            },
            'position': {
              'x': translation[0],
              'y': translation[1],
              'z': translation[2]
            },
            'scale': {
              'x': scale[0],
              'y': scale[1],
              'z': scale[2]
            }
          };

          for (const setting in settings) {
            for (const axis in settings[setting]) {
              if (settings[setting][axis] != null && settings[setting][axis] !== '') {
                if (setting === 'rotation') this.sceneMesh[setting][axis] = THREE.MathUtils.degToRad(settings[setting][axis]);
                else this.sceneMesh[setting][axis] = settings[setting][axis];
              }
            }
          }

          this.sceneMesh.name = "3d_scene";
          this.sceneMesh.castShadow = true;
          this.add(this.sceneMesh);

          this.sceneBoundingBox.setFromObject(this.sceneMesh);
          const size = new THREE.Vector3();
          this.sceneBoundingBox.getSize(size);
          this.floorWidth = size.x;
          this.floorHeight = size.y;

          resolve();
        },
        // called while loading is progressing
        (xhr) => {
          let percentBy5 = parseInt(xhr.loaded / xhr.total * 20) * 5;
          let percent = parseInt(xhr.loaded / xhr.total * 100);

          $(progressBar).removeClass(currentProgressClass);
          currentProgressClass = 'width' + percentBy5;
          $(progressBar).addClass(currentProgressClass);
          $(progressBar).attr('aria-valuenow', percent);
          $(progressBar).text('Scene: ' + percent + '%');
        },
        // called when loading has errors
        (error) => {
          console.error("Error loading glTF: " + error);
          reject(error);
        }
      );
    });
  }

  initializeCamera() {
    const { cameraZ, center } = this.computePerspectiveCameraPose(
      this.floorWidth, this.floorHeight, this.perspectiveCamera.fov);
    this.perspectiveCamera.position.set(center.x, center.y, cameraZ);
    this.perspectiveCamera.updateProjectionMatrix();
  }

  initializeScene() {
    this.initializeCamera();
    // Update the scale if the calibration points were loaded in before the map
    // FIXME: Improve the loading flow so that the calibration points are loaded after the map
    this.updateCalibrationPointScale();

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.6);
    directionalLight.position.set(-this.perspectiveCamera.position.x,
                                  -this.perspectiveCamera.position.y,
                                  this.perspectiveCamera.position.z * 2);
    this.add(directionalLight);

    this.orbitControls.target.set(this.floorWidth / 2, this.floorHeight / 2, 1);
  }
}

export { Viewport };
