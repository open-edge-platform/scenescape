// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import * as THREE from "/static/assets/three.module.js";

export default function AssetManager(scene, subscribeToTracking) {
  // Initialize cache of tracked objects
  let objectCache = {};
  // Object to hold the collection of marks across scene updates
  let marks = {};

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
    let mark = new THREE.Object3D();

    if (typeof objectCache[object.category] != "undefined") {
      addDefaultMark(mark, objectCache, object.category);
    } else {
      addDefaultMark(mark, objectCache, "unknown");
      mark.children[0].name = object.category;
    }

    // Place the mark in the scene
    scene.add(mark);

    return mark.id;
  }

  function addDefaultMark(mark, objectCache, category) {
    mark.add(objectCache[category].clone());
    mark.category = category;
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

      delete marks[markId]; // Delete from the marks object
      scene.remove(del); // Remove from the scene
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
    });
  }

  function loadAssets(gltfLoader) {
    // Add a default box for unknown objects not defined in the object library
    addDefaultGeometryToCache("unknown", "green", 1);

    let assets = document.querySelectorAll(".asset");
    let assetsToLoad = 0;

    // Determine how many assets to load
    assets.forEach((asset) => {
      asset = JSON.parse(asset.value);

      if ("url" in asset) {
        assetsToLoad++;
      }
    });

    // Load assets
    assets.forEach((asset) => {
      asset = JSON.parse(asset.value);

      // If there's a 3D asset, its URL is available
      if ("url" in asset) {
        let progressWrapper = document.getElementById(
          "loader-progress-" + asset.name,
        );
        let progressBar = progressWrapper.querySelector(".progress-bar");
        let currentProgressClass = "width0";

        progressWrapper.classList.add("display-flex");
        progressWrapper.classList.remove("display-none");

        gltfLoader.load(
          asset.url,
          (gltf) => {
            gltf.scene.rotation.x = (asset.rotation[0] * Math.PI) / 180;
            gltf.scene.rotation.y = (asset.rotation[1] * Math.PI) / 180;
            gltf.scene.rotation.z = (asset.rotation[2] * Math.PI) / 180;
            gltf.scene.position.x = asset.translation[0];
            gltf.scene.position.y = asset.translation[1];
            gltf.scene.position.z = asset.translation[2];
            gltf.scene.name = asset.name;

            progressWrapper.classList.add("display-none");
            progressWrapper.classList.remove("display-flex");
            objectCache[asset.name] = gltf.scene;

            --assetsToLoad;

            if (assetsToLoad === 0) {
              subscribeToTracking();
            }
          },
          // called while loading is progressing
          (xhr) => {
            let percentBy5 = parseInt((xhr.loaded / xhr.total) * 20) * 5;
            let percent = parseInt((xhr.loaded / xhr.total) * 100);

            progressBar.classList.remove(currentProgressClass);
            currentProgressClass = "width" + percentBy5;
            progressBar.classList.add(currentProgressClass);
            progressBar.setAttribute("aria-valuenow", percent);
            progressBar.innerText = asset.name + ": " + percent + "%";
          },
          // called when loading has errors
          (error) => {
            console.log("Error loading glTF for " + asset.name + ": " + error);
          },
        );
      } else {
        addDefaultGeometryToCache(asset.name, asset.mark_color, asset.z_size);
      }
    });

    if (assetsToLoad === 0) {
      subscribeToTracking();
    }
  }

  return { loadAssets, plot, hideMarks };
}
