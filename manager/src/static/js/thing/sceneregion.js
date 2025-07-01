// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import ThingControls from '/static/js/thing/controls/thingcontrols.js';
import * as THREE from '/static/assets/three.module.js';
import validateInputControls from '/static/js/thing/controls/validateinputcontrols.js';

const MAX_HEIGHT = 10;
const MAX_OPACITY = 1;
const MAX_SEGMENTS = 65;

export default class SceneRegion extends THREE.Object3D {
  constructor(params) {
    super();
    this.name = params.name;
    this.region = params;
    this.points = [];
    this.isStaff = params.isStaff;
    this.regionType = null;

    if (this.region.area === 'scene') {
      this.region['points'] = []
      this.regionType = 'scene'
    }
    else if (this.region.area === 'circle') {
      this.regionType = 'circle'
    }
    else {
      this.regionType = 'poly'
    }
  }

  createCircle(x, y) {
    let cylinderGeometry = null;
    if (this.points.length > 0) {
      const shape = new THREE.Shape(this.points);
      cylinderGeometry = new THREE.ExtrudeGeometry(shape, this.extrudeSettings);
      const center = new THREE.Vector3(x, y, 0);
      cylinderGeometry.translate(center.x, center.y, center.z);
    }
    return cylinderGeometry;
  }

  createPoly() {
    let polyGeometry = null;
    if (this.points.length > 0) {
      const shape = new THREE.Shape(this.points);
      polyGeometry = new THREE.ExtrudeGeometry(shape, this.extrudeSettings);
    }
    return polyGeometry;
  }
  createShape() {
    this.extrudeSettings = {
      depth: this.height,
      bevelEnabled: false
    };
    this.setOpacity = true;
    this.material = new THREE.MeshLambertMaterial({
      color: this.color,
      transparent: true,
      opacity: this.opacity
    });
    this.scaleFactor = this.height;
    this.setPoints();

    if (this.regionType === 'poly') {
      const polyGeometry = this.createPoly();
      this.shape = new THREE.Mesh(polyGeometry, this.material);
    }

    if (this.regionType === 'circle') {
      let cylinderGeometry = null;
      if (this.region.hasOwnProperty("center")) {
        cylinderGeometry = this.createCircle(this.region.center[0], this.region.center[1])
      }
      else {
        cylinderGeometry = this.createCircle(this.region.x, this.region.y)
      }
      this.shape = new THREE.Mesh(cylinderGeometry, this.material);
    }
    // Set render order to ensure regions are rendered before blocks
    this.shape.renderOrder = 1;
    this.type = 'region';
  }

  setPoints() {
    if (this.region === null) {
      throw new Error("Region is invalid");
    }

    if (this.regionType === 'poly') {
      this.region.points.forEach(p => {
        p.push(0);
        this.points.push(new THREE.Vector3(...p));
      });
    }
    if (this.regionType === 'circle') {
      for (let i = 0; i <= MAX_SEGMENTS; i++) {
        const theta = (i / MAX_SEGMENTS) * Math.PI * 2;
        const x = this.region.radius * Math.cos(theta);
        const y = this.region.radius * Math.sin(theta);
        this.points.push(new THREE.Vector2(x, y));
      }
    }
  }

  changeGeometry(geometry) {
    if (this.hasOwnProperty('shape') && this.shape !== null) {
      this.shape.geometry.dispose();
      this.shape.geometry = geometry;
    }
    else {
      this.shape = new THREE.Mesh(geometry, this.material);
      this.add(this.shape);
    }
  }
  addObject(params) {
    this.color = params.color;
    this.drawObj = params.drawObj;
    this.opacity = params.opacity;
    this.maxHeight = MAX_HEIGHT;
    this.maxOpacity = MAX_OPACITY;
    this.scene = params.scene;
    this.height = params.height;
    this.regionsFolder = params.regionsFolder;
    this.visible = false;
    this.regionControls = new ThingControls(this);

    Object.assign(this, validateInputControls);
    this.regionControls.addArea();
    if (this.points && this.points.length > 0) {
      let x = this.points[0].x;
      let y = this.points[1].y;
      if (this.regionType === 'circle') {
        if (this.region.hasOwnProperty("center")) {
          x = this.region.center[0];
          y = this.region.center[1];
        }
        else {
          x = this.region.x;
          y = this.region.y;
        }
      }

      this.textPos = {
        x: x,
        y: y,
        z: this.height
      };
      this.drawObj.createTextObject(this.name, this.textPos)
        .then((textMesh) => {
          this.add(textMesh);
        });
    };
    this.regionControls.addToScene();
    this.regionControls.addControlPanel(this.regionsFolder);
    this.controlsFolder = this.regionControls.controlsFolder;
    this.disableFields(['name']);

    if (this.isStaff === null) {
      let fields = Object.keys(this.regionControls.panelSettings);
      this.disableFields(fields);
      this.executeOnControl('opacity', (control) => { control[0].domElement.classList.add('disabled')});
    }
  }

  createGeometry(data) {
    this.region = data;
    let geometry = null;
    if (data.area === 'circle') {
      this.regionType = 'circle';
      this.setPoints();
      geometry = this.createCircle(data.x, data.y);
      this.changeGeometry(geometry);
    }
    else if (data.area === 'poly') {
      this.regionType = 'poly';
      this.setPoints();
      geometry = this.createPoly();
      this.changeGeometry(geometry);
    }
    else {
      this.remove(this.shape);
      this.shape = null;
    }
  }

  updateShape(data) {
    this.regionControls.updateGeometry(data);
  }
}
