// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

/**
 * @file draw.js
 * @description This file defines the Draw module, which provides functions for drawing text
 * and other geometric objects in a 3D scene.
 */

"use strict";

import * as THREE from "/static/assets/three.module.js";
import ProjectedMaterial from "/static/assets/ProjectedMaterial.module.js";
import { TextGeometry } from "/static/examples/jsm/geometries/TextGeometry.js";
import { FontLoader } from "/static/examples/jsm/loaders/FontLoader.js";
import { mergeGeometries } from "/static/examples/jsm/utils/BufferGeometryUtils.js";
import {
  SPHERE_NUM_SEGMENTS,
  SPHERE_RADIUS,
  TEXT_FONT,
  TEXT_SIZE,
} from "/static/js/constants.js";
import {
  CSS2DRenderer,
  CSS2DObject,
} from "/static/examples/jsm/renderers/CSS2DRenderer.js";

const TEXT_MATERIAL = new THREE.MeshStandardMaterial({
  color: new THREE.Color("black"),
  transparent: false,
  opacity: 0.4,
});
const POINT_GEOMETRY = new THREE.SphereGeometry(
  SPHERE_RADIUS,
  SPHERE_NUM_SEGMENTS,
  SPHERE_NUM_SEGMENTS,
);

/**
 * Extracts the geometry from the given glTF object.
 * @param {THREE.GLTF} gltf - The glTF object to extract the geometry from.
 * @returns {THREE.BufferGeometry} The extracted geometry.
 */
function extractGeometry(gltf) {
  const geometries = [];
  gltf.updateWorldMatrix(true, true);
  const rootInverse = gltf.matrixWorld.clone().invert();
  gltf.traverse((child) => {
    if (child.isMesh) {
      const geometry = child.geometry.clone();
      const localToRoot = rootInverse.clone().multiply(child.matrixWorld);
      geometry.applyMatrix4(localToRoot);
      geometries.push(geometry);
    }
  });

  return mergeGeometries(geometries);
}

function createLabelRenderer(domElement) {
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
  return labelRenderer;
}

function createLabelElement(objectId, category) {
  const div = document.createElement("div");
  div.className = "asset-label";

  const header = document.createElement("div");
  header.className = "asset-label-id";
  header.textContent = `${category} #${objectId}`;

  const row = document.createElement("div");
  row.className = "asset-label-row";
  row.append("Dwell: ");

  const span = document.createElement("span");
  span.dataset.field = "dwell";
  span.textContent = "—";
  row.appendChild(span);

  div.appendChild(header);
  div.appendChild(row);
  return div;
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

function createMarkObject(object, objectCache) {
  const mark = new THREE.Object3D();

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
  return mark;
}

function updateLabelFields(markObject, fields) {
  const labelObj = markObject.getObjectByName("css2dLabel");
  if (!labelObj) return;
  const el = labelObj.element;

  for (const [field, value] of Object.entries(fields)) {
    let span = el.querySelector(`[data-field="${field}"]`);
    if (!span) {
      const row = document.createElement("div");
      row.className = "asset-label-row";
      row.innerHTML = `${field}: <span data-field="${field}"></span>`;
      el.appendChild(row);
      span = row.querySelector(`[data-field="${field}"]`);
    }
    span.textContent = value ?? "—";
  }
}

class Draw {
  constructor() {
    this.fontLoader = new FontLoader();
  }

  /**
   * Creates a text object with the given name and position.
   * @param {string} name - The name of the text object.
   * @param {THREE.Vector3} position - The position of the text object.
   * @returns {Promise<THREE.Mesh>} A promise that resolves with the text object.
   */
  createTextObject(name, position, size = TEXT_SIZE) {
    return new Promise((resolve, reject) => {
      this.fontLoader.load(
        TEXT_FONT,
        (font) => {
          const textOptions = {
            font: font,
            size: size,
            depth: 0.05,
            bevelEnabled: false,
          };
          const textGeometry = new TextGeometry(name, textOptions);
          const textMesh = new THREE.Mesh(textGeometry, TEXT_MATERIAL);
          textMesh.position.copy(position);
          textMesh.name = "textObject_" + name;

          resolve(textMesh);
        },
        undefined,
        (error) => {
          reject(error);
        },
      );
    });
  }

  /**
   * Creates a calibration point with the given name, position, and color.
   * @param {string} name - The name of the calibration point.
   * @param {THREE.Vector3} position - The position of the calibration point.
   * @param {string} color - The color of the calibration point.
   * @returns {THREE.Mesh} The calibration point object.
   */
  createCalibrationPoint(name, position, color) {
    const material = new THREE.MeshStandardMaterial({
      color: color,
      metalness: 0.5,
      emissive: color,
      emissiveIntensity: 0.5,
    });
    const sphere = new THREE.Mesh(POINT_GEOMETRY, material);
    sphere.position.copy(position);
    sphere.name = "calibrationPoint_" + name;
    return sphere;
  }

  /**
   * Creates a projection material for the given floor mesh and texture.
   * @param {THREE.PerspectiveCamera} projectionCamera - The camera which the texture will be
   * projected from.
   * @param {THREE.Mesh} floorMesh - The floor mesh of the scene.
   * @param {THREE.Texture} texture - The texture to project onto the floor mesh.
   * @returns {Array} An array containing the projected material
   * and the mesh with the projection material applied.
   */
  createProjectionMaterial(projectionCamera, floorMesh, texture) {
    const projectedMaterial = new ProjectedMaterial({
      camera: projectionCamera,
      texture: texture,
      opacity: 1.0,
      blending: THREE.NormalBlending,
      transparent: true,
    });
    const physicalMaterial = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      opacity: 0.01,
      blending: THREE.NormalBlending,
      transparent: true,
    });

    const geometry = extractGeometry(floorMesh);
    geometry.computeVertexNormals();

    const mesh = new THREE.Mesh(geometry, physicalMaterial);
    mesh.position.copy(floorMesh.position);
    mesh.rotation.copy(floorMesh.rotation);
    mesh.scale.copy(floorMesh.scale);

    const materials = [physicalMaterial, projectedMaterial];
    // allows multiple materials to be used with the geometry.
    for (let i = 0; i < materials.length; i++) {
      geometry.addGroup(0, Infinity, i);
    }
    mesh.material = materials;
    mesh.castShadow = true;
    projectedMaterial.project(mesh);

    return [projectedMaterial, mesh];
  }
}

export {
  Draw,
  createLabelRenderer,
  createMarkObject,
  createLabelElement,
  updateLabelFields,
};
