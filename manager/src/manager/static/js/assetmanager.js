// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import * as THREE from "/static/assets/three.module.js";
import {
  CSS2DRenderer,
  CSS2DObject,
} from "/static/examples/jsm/renderers/CSS2DRenderer.js";
import RESTClient from "/static/js/restclient.js";
import { REST_URL, SUCCESS } from "/static/js/constants.js";

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

  let labelMode = "hover";

  let hoveredMarkId = null;

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(domElement.clientWidth, domElement.clientHeight);
  labelRenderer.domElement.style.position = "absolute";
  labelRenderer.domElement.style.top = "0";
  labelRenderer.domElement.style.pointerEvents = "none";
  domElement.parentElement.appendChild(labelRenderer.domElement);

  const resizeObserver = new ResizeObserver(() => {
    labelRenderer.setSize(domElement.clientWidth, domElement.clientHeight);
  });
  resizeObserver.observe(domElement);

  if (!document.getElementById("asset-label-style")) {
    const style = document.createElement("style");
    style.id = "asset-label-style";
    style.textContent = `
      .asset-label {
        background: rgba(0, 0, 0, 0.72);
        color: #fff;
        font-family: system-ui, sans-serif;
        font-size: 12px;
        line-height: 1.5;
        padding: 5px 9px;
        border-radius: 6px;
        white-space: nowrap;
        pointer-events: none;
        transform: translateX(-50%);
        border: 1px solid rgba(255,255,255,0.15);
        opacity: 0;
        transition: opacity 0.15s ease;
      }
      .asset-label.visible {
        opacity: 1;
      }
      .asset-label-id {
        font-weight: 600;
        margin-bottom: 2px;
      }
      .asset-label-row {
        color: rgba(255,255,255,0.75);
        font-size: 11px;
      }
      .asset-label-row span {
        color: #fff;
        font-weight: 500;
      }
    `;
    document.head.appendChild(style);
  }

  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  domElement.addEventListener("mousemove", (e) => {
    if (labelMode !== "hover") return;

    const rect = domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, activeCamera);

    const targets = [];
    for (const mark of Object.values(marks)) {
      const obj = scene.getObjectById(mark.id);
      if (obj) {
        const model = obj.getObjectByName("model");
        if (model)
          model.traverse((child) => {
            if (child.isMesh) targets.push(child);
          });
      }
    }

    const intersects = raycaster.intersectObjects(targets, false);

    let newHoverId = null;
    if (intersects.length > 0) {
      let root = intersects[0].object;
      while (root.parent && root.parent !== scene) root = root.parent;
      const matchedMark = Object.values(marks).find(m => m.id === root.id);
      newHoverId = matchedMark ? root.id : null;
    }

    if (newHoverId !== hoveredMarkId) {
      if (hoveredMarkId !== null) {
        const old = scene.getObjectById(hoveredMarkId);
        if (old) setLabelVisible(old, false);
      }
      hoveredMarkId = newHoverId;
      if (hoveredMarkId !== null) {
        const next = scene.getObjectById(hoveredMarkId);
        if (next) setLabelVisible(next, true);
      }
    }
  });

  domElement.addEventListener("mouseleave", () => {
    if (hoveredMarkId !== null) {
      const obj = scene.getObjectById(hoveredMarkId);
      if (obj) setLabelVisible(obj, false);
      hoveredMarkId = null;
    }
  });

  function createLabelElement(objectId, category) {
    const div = document.createElement("div");
    div.className = "asset-label";
    div.innerHTML = `
      <div class="asset-label-id">${category} #${objectId}</div>
      <div class="asset-label-row">Dwell: <span data-field="dwell">—</span></div>
    `;
    return div;
  }

  function setLabelVisible(markObject, visible) {
    const labelObj = markObject.getObjectByName("css2dLabel");
    if (!labelObj) return;
    const el = labelObj.element;
    if (visible) {
      el.style.display = "block";
      requestAnimationFrame(() => el.classList.add("visible"));
    } else {
      el.classList.remove("visible");
      setTimeout(() => (el.style.display = "none"), 150);
    }
  }

  function updateLabelData(markObject, obj) {
    const labelObj = markObject.getObjectByName("css2dLabel");
    if (!labelObj) return;
    const el = labelObj.element;

    const set = (field, val) => {
      const span = el.querySelector(`[data-field="${field}"]`);
      if (span) span.textContent = val ?? "—";
    };

    if (obj.regions && Object.keys(obj.regions).length > 0) {
      Object.entries(obj.regions).forEach(([regionId, regionData]) => {
        if (regionData.entered) {
          set(
            "dwell",
            regionData.dwell != null ? `${regionData.dwell.toFixed(1)}s` : "—",
          );
        }
      });
    } else {
      set("dwell", "—");
    }
  }

  function setLabelMode(mode) {
    labelMode = mode;
    hoveredMarkId = null;

    for (const mark of Object.values(marks)) {
      const obj = scene.getObjectById(mark.id);
      if (obj) setLabelVisible(obj, mode === "all");
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

  function colorFromId(id) {
    const hex = String(id)
      .replace(/[^0-9a-f]/gi, "")
      .padEnd(6, "0")
      .substring(0, 6);

    return new THREE.Color("#" + hex);
  }

  function createIndicator(objectId) {
    const color = colorFromId(objectId);

    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;

    const ctx = canvas.getContext("2d");

    // Draw downward triangle
    ctx.fillStyle = "#" + color.getHexString();
    ctx.beginPath();
    ctx.moveTo(32, 56); // bottom point
    ctx.lineTo(8, 8); // top left
    ctx.lineTo(56, 8); // top right
    ctx.closePath();
    ctx.fill();

    const texture = new THREE.CanvasTexture(canvas);

    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
      }),
    );
    sprite.name = "indicator";
    sprite.scale.set(1, 1, 1);
    return sprite;
  }

  // Create a mark geometry
  function createGeometry(object) {
    let mark = new THREE.Object3D();

    const model = new THREE.Object3D();
    model.name = "model";
    model.add((objectCache[object.category] ?? objectCache["unknown"]).clone());

    const indicator = createIndicator(object.id);
    indicator.name = "indicator";
    const indicatorHolder = new THREE.Object3D();
    indicatorHolder.add(indicator);

    const labelEl = createLabelElement(object.id, object.category);
    const labelObj = new CSS2DObject(labelEl);
    labelObj.name = "css2dLabel";
    labelObj.position.set(0, 0, 0);

    mark.add(model);
    mark.add(indicatorHolder);
    mark.add(labelObj);

    scene.add(mark);
    return mark.id;
  }

  function hideMarks() {
    for (const mark of Object.values(marks)) {
      scene.getObjectById(mark.id).visible = false;
    }
  }

  // Plot marks on the scene
  function plot(msg) {
    // SceneScape sends only current marks, so we need to determine
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
        if (labelMode === "all") setLabelVisible(thisMark, true);
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
                if (assetsToLoad === 0 && reload === false)
                  subscribeToTracking();
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

        if (assetsToLoad === 0 && reload === false) subscribeToTracking();
      })
      .catch((error) => {
        console.error("Error fetching assets:", error);
      });
  }

  return { loadAssets, plot, hideMarks, renderLabels, setLabelMode, setCamera };
}
