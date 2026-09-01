// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import * as THREE from "/static/assets/three.module.js";
import {
  SPHERE_NUM_SEGMENTS,
  SPHERE_RADIUS,
  SCENE_MESH_NAMES,
} from "/static/js/constants.js";
import SceneCamera from "/static/js/thing/scenecamera.js";

function isMeshToProjectOn(intersect) {
  if (
    SCENE_MESH_NAMES.some((name) =>
      intersect.object.name.toLowerCase().includes(name),
    )
  ) {
    return true;
  }

  let parent = intersect.object.parent;
  while (parent) {
    if (parent.name === "3d_scene") {
      return true;
    }
    parent = parent.parent;
  }

  return false;
}

function SetupMarkHover(scene, domElement, marks, getCamera) {
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let labelMode = "hover";
  let hoveredMarkId = null;
  const hideTimers = new WeakMap();

  function getMarkTargets() {
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
    return targets;
  }

  function getHoveredMarkId(intersects) {
    if (intersects.length === 0) return null;
    let root = intersects[0].object;
    while (root.parent && root.parent !== scene) root = root.parent;
    const matched = Object.values(marks).find((m) => m.id === root.id);
    return matched ? root.id : null;
  }

  function setLabelVisibility(markObject, visible) {
    const labelObj = markObject.getObjectByName("css2dLabel");
    if (!labelObj) return;
    const el = labelObj.element;

    const existingTimer = hideTimers.get(el);
    if (existingTimer) {
      clearTimeout(existingTimer);
      hideTimers.delete(el);
    }

    if (visible) {
      el.style.display = "block";
      requestAnimationFrame(() => el.classList.add("visible"));
    } else {
      el.classList.remove("visible");
      hideTimers.set(
        el,
        setTimeout(() => {
          el.style.display = "none";
          hideTimers.delete(el);
        }, 150),
      );
    }
  }

  domElement.addEventListener("mousemove", (e) => {
    if (labelMode !== "hover") return;

    const rect = domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, getCamera());
    const newHoverId = getHoveredMarkId(
      raycaster.intersectObjects(getMarkTargets(), false),
    );
    if (newHoverId !== hoveredMarkId) {
      if (hoveredMarkId !== null) {
        const old = scene.getObjectById(hoveredMarkId);
        if (old) setLabelVisibility(old, false);
      }
      hoveredMarkId = newHoverId;
      if (hoveredMarkId !== null) {
        const next = scene.getObjectById(hoveredMarkId);
        if (next) setLabelVisibility(next, true);
      }
    }
  });

  domElement.addEventListener("mouseleave", () => {
    if (hoveredMarkId !== null) {
      const obj = scene.getObjectById(hoveredMarkId);
      if (obj) setLabelVisibility(obj, false);
      hoveredMarkId = null;
    }
  });

  function setLabelMode(mode) {
    labelMode = mode;
    hoveredMarkId = null;
    for (const mark of Object.values(marks)) {
      const obj = scene.getObjectById(mark.id);
      if (obj) setLabelVisibility(obj, mode === "all");
    }
  }
  return { setLabelVisibility, setLabelMode, getLabelMode: () => labelMode };
}

function SetupInteractions(
  scene,
  renderer,
  raycaster,
  orbitControls,
  sceneViewCamera,
) {
  // Define camera matrix and distortion coefficients
  let selectedCamera = null;
  let pendingClick = null;

  function setSelectedCamera(obj, openFolder = false) {
    if (selectedCamera !== obj) {
      if (selectedCamera) selectedCamera.unselect();
      selectedCamera = obj;
      if (selectedCamera !== null) selectedCamera.onClick(openFolder);
    } else {
      // Same camera clicked - handle folder toggle or deselect
      if (selectedCamera !== null) selectedCamera.onClick(openFolder);
      if (!openFolder) {
        selectedCamera.unselect();
        selectedCamera = null;
      }
    }

    return;
  }

  function unsetSelectedCamera(obj) {
    if (selectedCamera !== null && selectedCamera === obj) {
      selectedCamera.unselect();
      selectedCamera = null;
    }
  }

  //On click will set the current camera. Every other event will be delegated to be handled by the selected camera.
  function onClick(event) {
    if (pendingClick) {
      clearTimeout(pendingClick);
      pendingClick = 0;
    }

    if (event.detail === 1) {
      pendingClick = setTimeout(() => {
        let mouse = {
          x: (event.clientX / renderer.domElement.clientWidth) * 2 - 1,
          y: -(event.clientY / renderer.domElement.clientHeight) * 2 + 1,
        };

        raycaster.setFromCamera(mouse, sceneViewCamera);
        // calculate objects intersecting the picking ray
        if (scene) {
          const intersects = raycaster.intersectObjects(scene.children);
          for (const intersect of intersects) {
            if (intersect.object.type === "CameraHelper") {
              let obj = intersect.object.parent;
              if (obj && obj instanceof SceneCamera) {
                setSelectedCamera(obj, true);
              }
            }
          }
        }
      }, 200);
    }
  }

  const sphereGeometry = new THREE.SphereGeometry(
    SPHERE_RADIUS,
    SPHERE_NUM_SEGMENTS,
    SPHERE_NUM_SEGMENTS,
  );
  const material = new THREE.MeshNormalMaterial();
  const sphereMesh = new THREE.Mesh(sphereGeometry, material);

  function onDoubleClick(event) {
    if (selectedCamera === null) return;

    let mouse = {
      x: (event.clientX / renderer.domElement.clientWidth) * 2 - 1,
      y: -(event.clientY / renderer.domElement.clientHeight) * 2 + 1,
    };
    raycaster.setFromCamera(mouse, sceneViewCamera);

    const intersects = raycaster.intersectObjects(scene.children);
    //intersects - array of (distance, point of intersection, face, object ray intersects with)

    for (const intersect of intersects) {
      if (isMeshToProjectOn(intersect)) {
        const normal = new THREE.Vector3();
        normal.copy(intersect.face.normal); // face normal in object coordinate system
        normal.transformDirection(intersect.object.matrixWorld); // face normal in parent coordinate system
        const sphere = sphereMesh.clone();
        sphere.name = "drag_sphere";
        sphere.position.copy(intersect.point);
        sphere.position.addScaledVector(normal, 0.0);

        selectedCamera.onDoubleClick(sphere);
        return;
      }
    }
  }

  function onRightClick(event) {
    event.preventDefault();
    if (selectedCamera === null) return;

    let mouse = {
      x: (event.clientX / renderer.domElement.clientWidth) * 2 - 1,
      y: -(event.clientY / renderer.domElement.clientHeight) * 2 + 1,
    };
    raycaster.setFromCamera(mouse, sceneViewCamera);

    const intersects = raycaster.intersectObjects(scene.children);
    //intersects - array of (distance, point of intersection, face, object ray intersects with)

    for (const intersect of intersects) {
      if (intersect.object.name.includes("drag_sphere")) {
        const objectHit = intersect.object;
        selectedCamera.onRightClick(objectHit);
        return;
      }
    }

    if (selectedCamera) {
      selectedCamera.unselect();
      selectedCamera = null;
    }
  }

  let dragging = false;
  let dragItem = null;
  function onMouseDown(event) {
    dragging = true;
    let mouse = {
      x: (event.clientX / renderer.domElement.clientWidth) * 2 - 1,
      y: -(event.clientY / renderer.domElement.clientHeight) * 2 + 1,
    };
    raycaster.setFromCamera(mouse, sceneViewCamera);
    if (scene) {
      const intersects = raycaster.intersectObjects(scene.children);
      for (const intersect of intersects) {
        if (intersect.object.name.includes("drag_sphere")) {
          const objectHit = intersect.object;
          dragItem = objectHit;

          orbitControls.enabled = false;
          return;
        }
      }
    }
  }

  function onMouseMove(event) {
    if (dragging) {
      renderer.domElement.removeEventListener("click", onClick);
      if (dragItem) {
        let mouse = {
          x: (event.clientX / renderer.domElement.clientWidth) * 2 - 1,
          y: -(event.clientY / renderer.domElement.clientHeight) * 2 + 1,
        };
        raycaster.setFromCamera(mouse, sceneViewCamera);

        if (scene) {
          const intersects = raycaster.intersectObjects(scene.children);
          for (const intersect of intersects) {
            if (isMeshToProjectOn(intersect)) {
              const normal = new THREE.Vector3();
              normal.copy(intersect.face.normal);
              normal.transformDirection(intersect.object.matrixWorld);

              dragItem.position.copy(intersect.point);
              let camera = dragItem.parent.parent;
              camera.performCameraCalib();
              return;
            }
          }
        }
      }
    }
  }

  function onMouseUp() {
    if (dragging) {
      dragging = false;
      dragItem = null;
      orbitControls.enabled = true;
      setTimeout(() => {
        renderer.domElement.addEventListener("click", onClick);
      }, 10);
    }
  }

  renderer.domElement.addEventListener("mousemove", onMouseMove);
  renderer.domElement.addEventListener("mousedown", onMouseDown);
  renderer.domElement.addEventListener("mouseup", onMouseUp);
  renderer.domElement.addEventListener("dblclick", onDoubleClick);
  renderer.domElement.addEventListener("click", onClick);
  renderer.domElement.addEventListener("contextmenu", onRightClick);

  return { setSelectedCamera, unsetSelectedCamera };
}

export { isMeshToProjectOn, SetupInteractions, SetupMarkHover };
