// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import ThingControls from "/static/js/thing/controls/thingcontrols.js";
import * as THREE from "/static/assets/three.module.js";
import validateInputControls from "/static/js/thing/controls/validateinputcontrols.js";

const MAX_HEIGHT = 5;

export default class SceneTripwire extends THREE.Object3D {
  constructor(params) {
    super();
    this.name = params.name;
    this.tripwire = params;
    this.points = [];
    this.isStaff = params.isStaff;
  }

  createShape() {
    this.setPoints();
    this.scaleFactor = this.height;
    this.setOpacity = false;
    this.material = new THREE.LineBasicMaterial({ color: this.color });
    const tripwireGeometry = new THREE.BufferGeometry();
    tripwireGeometry.setFromPoints(this.points);
    this.shape = new THREE.Line(tripwireGeometry, this.material);
    this.type = "tripwire";
  }

  setPoints() {
    if (this.tripwire === null || typeof this.tripwire.points === "undefined") {
      throw new Error("Tripwire is invalid");
    }

    this.points.push(
      new THREE.Vector3(
        this.tripwire.points[0][0],
        this.tripwire.points[0][1],
        0,
      ),
    );
    this.points.push(
      new THREE.Vector3(
        this.tripwire.points[1][0],
        this.tripwire.points[1][1],
        0,
      ),
    );
    this.points.push(
      new THREE.Vector3(
        this.tripwire.points[1][0],
        this.tripwire.points[1][1],
        this.height,
      ),
    );
    this.points.push(
      new THREE.Vector3(
        this.tripwire.points[0][0],
        this.tripwire.points[0][1],
        this.height,
      ),
    );
    this.points.push(
      new THREE.Vector3(
        this.tripwire.points[0][0],
        this.tripwire.points[0][1],
        0,
      ),
    );
  }

  addObject(params) {
    this.color = params.color;
    this.drawObj = params.drawObj;
    this.scene = params.scene;
    this.height = params.height;
    this.tripwireFolder = params.tripwireFolder;
    this.maxHeight = MAX_HEIGHT;
    this.visible = false;
    this.tripwireControls = new ThingControls(this);
    Object.assign(this, validateInputControls);
    this.tripwireControls.addArea();
    this.textPos = {
      x: this.points[0].x,
      y: this.points[0].y,
      z: this.height,
    };
    this.drawObj.createTextObject(this.name, this.textPos).then((textMesh) => {
      this.add(textMesh);
    });
    this.tripwireControls.addToScene();
    this.tripwireControls.addControlPanel(this.tripwireFolder);
    this.controlsFolder = this.tripwireControls.controlsFolder;
    this.disableFields(["name"]);

    if (this.isStaff === null) {
      let fields = Object.keys(this.tripwireControls.panelSettings);
      this.disableFields(fields);
    }
  }

  createGeometry(data) {
    this.tripwire = data;
    this.setPoints();
    this.shape.geometry.setFromPoints(this.points);
  }

  updateShape(data) {
    this.tripwireControls.updateGeometry(data);
  }
}
