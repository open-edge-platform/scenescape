// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

/**
 * @file draw.js
 * @description This file defines the Draw module, which provides functions for drawing text
 * and other geometric objects in a 3D scene.
 */

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
  gltf.traverse((child) => {
    if (child.isMesh) {
      geometries.push(child.geometry);
    }
  });

  return mergeGeometries(geometries);
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

export { Draw };
