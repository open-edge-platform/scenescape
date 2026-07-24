// SPDX-FileCopyrightText: (C) 2023 - 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import * as THREE from "/static/assets/three.module.js";
import RESTClient from "/static/js/restclient.js";
import { REST_URL, SUCCESS } from "/static/js/constants.js";
import {
  createLabelRenderer,
  createMarkObject,
  updateLabelFields,
} from "/static/js/draw.js";
import { SetupMarkHover } from "/static/js/interactions.js";

export default function AssetManager(
  scene,
  subscribeToTracking,
  camera,
  domElement,
) {
  let authToken = `Token ${document.getElementById("auth-token").value}`;
  let restclient = new RESTClient(REST_URL, authToken);
  let activeCamera = camera;
  let objectCache = {};
  let marks = {};

  const labelRenderer = createLabelRenderer(domElement);
  const { setLabelVisible, setLabelMode, getLabelMode } = SetupMarkHover(
    scene,
    domElement,
    marks,
    () => activeCamera,
  );

  function updateLabelData(markObject, obj) {
    if (obj.regions && Object.keys(obj.regions).length > 0) {
      Object.entries(obj.regions).forEach(([regionId, regionData]) => {
        if (regionData.entered) {
          updateLabelFields(markObject, {
            dwell:
              regionData.dwell != null
                ? `${regionData.dwell.toFixed(1)}s`
                : null,
          });
        }
      });
    } else {
      updateLabelFields(markObject, { dwell: null });
    }
  }

  function addDefaultGeometryToCache(name, color, depth) {
    let material = new THREE.MeshLambertMaterial({
      color: new THREE.Color(color),
      opacity: 0.8,
      transparent: true,
    });
    let boxGeometry = new THREE.BoxGeometry(1, 1, 1);
    let defaultBoxMesh = new THREE.Mesh(boxGeometry, material);
    defaultBoxMesh.name = name;

    objectCache[name] = defaultBoxMesh;
  }

  // Create a mark geometry
  function createGeometry(object) {
    const mark = createMarkObject(object, objectCache);
    scene.add(mark);
    return mark.id;
  }

  // Switch object visibility to current 'tracked object' button's value
  function setMarksVisibility(shouldShow) {
    for (const mark of Object.values(marks)) {
      const obj = scene.getObjectById(mark.id);
      if (obj) {
        obj.visible = shouldShow;
      }
    }
  }

  // Plot marks on the scene
  function plot(msg) {
    // Scenescape sends only current marks, so we need to determine
    // which old marks are not in the current update and remove them

    // Create a set based on the current keys (object IDs) of the global
    // marks object
    let oldMarks = new Set(Object.keys(marks));
    let newMarks = new Set();

    // Add new marks from the current message into the newMarks set
    msg.objects.forEach((obj) => newMarks.add(String(obj.id)));

    // Remove any newMarks from oldMarks, leaving only expired marks
    newMarks.forEach((obj) => oldMarks.delete(obj));

    function deleteMark(markId) {
      let val = marks[markId];
      let del = scene.getObjectById(val.id);

      // Clean up CSS2D label DOM element before removing from scene
      // Delete from the marks object
      // Remove from the scene
      if (del) {
        const labelObj = del.getObjectByName("css2dLabel");
        if (labelObj && labelObj.element && labelObj.element.parentNode) {
          labelObj.element.parentNode.removeChild(labelObj.element);
        }
      }

      delete marks[markId];
      scene.remove(del);
    }

    // Remove oldMarks from both the scene and the marks collection
    oldMarks.forEach((markId) => deleteMark(markId));

    // Plot each object in the message
    msg.objects.forEach((obj) => {
      let mark = marks[obj.id];
      if (mark && mark.category != obj.category) {
        deleteMark(obj.id);
        mark = null;
      }

      if (!mark) {
        // Otherwise, add new mark
        let id = createGeometry(obj);

        // Store the mark in the global marks object for future use
        mark = marks[obj.id] = { id: id, category: obj.category };
      }

      let thisMark = scene.getObjectById(mark.id);
      // Change the position using the object's translation vector
      thisMark.position.set(...obj.translation);

      if (obj.rotation) {
        const qt = new THREE.Quaternion().fromArray(obj.rotation);
        thisMark.quaternion.copy(qt);
      }

      let scale = new THREE.Vector3(1, 1, 1);
      let translate;
      if (obj.asset_scale) {
        scale.fromArray(Array(3).fill(obj.asset_scale));
        translate = 0;
      } else if (obj.size) {
        scale.fromArray(obj.size);
        translate = scale.z / 2;
      }
      thisMark.translateZ(translate);
      thisMark.scale.copy(scale);
      const model = thisMark.getObjectByName("model");
      const indicator = thisMark.getObjectByName("indicator");
      const labelObj = thisMark.getObjectByName("css2dLabel");

      if (model && indicator) {
        model.updateWorldMatrix(true, true);
        const box = new THREE.Box3().setFromObject(model);
        const localBox = box
          .clone()
          .applyMatrix4(thisMark.matrixWorld.clone().invert());
        const top = localBox.max.z;
        indicator.position.z = top + 0.5;

        // Position label just above the indicator
        if (labelObj) {
          labelObj.position.z = top + 1.2;
        }
      }

      // Update label fields with latest data from the message
      if (labelObj) {
        updateLabelData(thisMark, obj);
        if (getLabelMode() === "all") setLabelVisible(thisMark, true);
      }
    });
  }

  function renderLabels() {
    for (const mark of Object.values(marks)) {
      const obj = scene.getObjectById(mark.id);
      if (obj) {
        const labelObj = obj.getObjectByName("css2dLabel");
        if (labelObj && labelObj.element) {
          if (!obj.visible && labelObj.element.style.display !== "none") {
            labelObj.element.style.display = "none";
          }
        }
      }
    }
    labelRenderer.render(scene, activeCamera);
  }

  function setCamera(newCamera) {
    activeCamera = newCamera;
    labelRenderer.setSize(domElement.clientWidth, domElement.clientHeight);
  }

  function loadAssets(gltfLoader, reload = false) {
    // Add a default box for unknown objects not defined in the object library
    addDefaultGeometryToCache("unknown", "green", 1);

    restclient
      .getAssets({})
      .then((response) => {
        if (response.statusCode !== SUCCESS) {
          console.error("Failed to load assets:", response);
          return;
        }

        let assets = response.content.results;

        // Determine how many assets have URLs
        let assetsToLoad = assets.filter((a) => a.model_3d).length;

        // Load each asset
        assets.forEach((asset) => {
          if (asset.model_3d) {
            let progressWrapper = document.getElementById(
              "loader-progress-" + asset.name,
            );
            let progressBar = progressWrapper.querySelector(".progress-bar");
            let currentProgressClass = "width0";

            progressWrapper.classList.add("display-flex");
            progressWrapper.classList.remove("display-none");

            gltfLoader.load(
              asset.model_3d,
              (gltf) => {
                gltf.scene.rotation.x = (asset.rotation_x * Math.PI) / 180;
                gltf.scene.rotation.y = (asset.rotation_y * Math.PI) / 180;
                gltf.scene.rotation.z = (asset.rotation_z * Math.PI) / 180;
                gltf.scene.position.x = asset.translation_x;
                gltf.scene.position.y = asset.translation_y;
                gltf.scene.position.z = asset.translation_z;
                gltf.scene.name = asset.name;

                progressWrapper.classList.add("display-none");
                progressWrapper.classList.remove("display-flex");
                objectCache[asset.name] = gltf.scene;

                --assetsToLoad;

                if (assetsToLoad === 0 && reload === false) {
                  subscribeToTracking();
                }
              },
              // Progress callback
              (xhr) => {
                let percentBy5 = parseInt((xhr.loaded / xhr.total) * 20) * 5;
                let percent = parseInt((xhr.loaded / xhr.total) * 100);

                progressBar.classList.remove(currentProgressClass);
                currentProgressClass = "width" + percentBy5;
                progressBar.classList.add(currentProgressClass);
                progressBar.setAttribute("aria-valuenow", percent);
                progressBar.innerText = asset.name + ": " + percent + "%";
              },
              // Error callback
              (error) => {
                console.log(
                  "Error loading glTF for " + asset.name + ": " + error,
                );
              },
            );
          } else {
            addDefaultGeometryToCache(
              asset.name,
              asset.mark_color,
              asset.z_size,
            );
          }
        });

        if (assetsToLoad === 0 && reload === false) {
          subscribeToTracking();
        }
      })
      .catch((error) => {
        console.error("Error fetching assets:", error);
      });
  }

  return {
    loadAssets,
    plot,
    setMarksVisibility,
    renderLabels,
    setLabelMode,
    setCamera,
  };
}
