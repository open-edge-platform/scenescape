// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import * as THREE from "/static/assets/three.module.js";
import ThingControls from "/static/js/thing/controls/thingcontrols.js";
import thingTransformControls from "/static/js/thing/controls/thingtransformcontrols.js";
import { SUCCESS } from "/static/js/constants.js";

const RADAR_MARKER_COLOR = 0xff8800;
const RADAR_AXES_SIZE_M = 3;
const RADAR_BORESIGHT_LEN_M = 8;

/**
 * Visualize a first-class radar sensor pose in the scene 3D view.
 *
 * Pose uses the same Scenescape Y-down → Three.js Y-up flip as cameras so
 * radar and camera markers share one scene frame. Local +X is radar
 * boresight (forward).
 */
export default class SceneRadar extends THREE.Object3D {
  constructor(params) {
    super();
    Object.assign(this, thingTransformControls);
    this.radarUID = params.uid;
    this.name = params.name || params.uid || "radar";
    this.isStoredInDB = params.isStoredInDB;
    this.isStaff = params.isStaff;
    this.flipCoordSystem = true;
    this.radarPosition =
      "translation" in params
        ? new THREE.Vector3(...params.translation)
        : new THREE.Vector3(0, 0, 0);
    this.radarRotation =
      "rotation" in params
        ? new THREE.Euler(
            ...params.rotation.map((deg) => THREE.MathUtils.degToRad(deg)),
          )
        : new THREE.Euler(0, 0, 0);
    this.addRadarMarker();
  }

  addRadarMarker() {
    this.radarFrame = new THREE.Object3D();
    this.radarFrame.name = this.name + "-frame";
    this.radarFrame.position.copy(this.radarPosition);
    this.radarFrame.rotation.copy(this.radarRotation);
    this.togglePoseYupYdown(this.radarFrame);

    const axes = new THREE.AxesHelper(RADAR_AXES_SIZE_M);
    axes.name = this.name + "-axes";
    this.radarFrame.add(axes);

    // Radar-local +X is forward / boresight.
    const boresight = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(0, 0, 0),
      RADAR_BORESIGHT_LEN_M,
      RADAR_MARKER_COLOR,
      1.2,
      0.6,
    );
    boresight.name = this.name + "-boresight";
    this.radarFrame.add(boresight);

    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.6, 20, 20),
      new THREE.MeshBasicMaterial({ color: RADAR_MARKER_COLOR }),
    );
    marker.name = this.name + "-marker";
    this.radarFrame.add(marker);

    // Small disk in the XY plane to suggest a mounted radar panel.
    const panel = new THREE.Mesh(
      new THREE.CylinderGeometry(1.2, 1.2, 0.15, 24),
      new THREE.MeshBasicMaterial({
        color: RADAR_MARKER_COLOR,
        transparent: true,
        opacity: 0.55,
      }),
    );
    panel.rotation.z = Math.PI / 2;
    panel.name = this.name + "-panel";
    this.radarFrame.add(panel);

    this.add(this.radarFrame);
  }

  get transformObject() {
    return this.radarFrame;
  }

  addObject(params) {
    this.drawObj = params.drawObj;
    this.scene = params.scene;
    this.renderer = params.renderer;
    this.sceneViewCamera = params.sceneViewCamera;
    this.orbitControls = params.orbitControls;

    this.drawObj
      .createTextObject(this.name, new THREE.Vector3(0, 0, 1.2))
      .then((textMesh) => {
        this.radarFrame.add(textMesh);
      });

    this.radarControls = new ThingControls(this);
    this.radarControls.addToScene();
    this.addControlPanel(params.radarsFolder);

    if (this.isStaff && params.sceneViewCamera && params.orbitControls) {
      this.addDragControls(params.sceneViewCamera, params.orbitControls);
      this.setTransformControlVisibility(false);
    }
  }

  addControlPanel(radarsFolder) {
    if (!radarsFolder) {
      return;
    }
    this.controlsFolder = radarsFolder.addFolder(this.name);
    this.controlsFolder.$title.setAttribute("id", this.name + "-control-panel");

    const panelSettings = {
      "show radar": true,
      "look at radar": () => this.focusView(),
      save: () => this.saveSettings(),
    };

    let control = this.controlsFolder
      .add(panelSettings, "show radar")
      .onChange((visible) => {
        this.visible = visible;
      });
    control.$widget.firstChild.id = this.name.concat("-", "show-radar");

    control = this.controlsFolder.add(panelSettings, "look at radar");
    control.$button.id = this.name.concat("-", "look-at-radar");

    if (this.isStaff) {
      this.addPoseControls(panelSettings);
      control = this.controlsFolder.add(panelSettings, "save");
      control.$button.id = this.name.concat("-", "save-radar");
      control.domElement.classList.add("disabled");
      this.saveControl = control;
    }

    this.controlsFolder.close();
  }

  updateSaveButton() {
    if (this.saveControl) {
      this.saveControl.domElement.classList.remove("disabled");
    }
  }

  focusView() {
    if (!this.orbitControls || !this.radarFrame) {
      return;
    }
    const target = new THREE.Vector3();
    this.radarFrame.getWorldPosition(target);
    this.orbitControls.target.copy(target);
    this.orbitControls.update();
  }

  async saveSettings() {
    if (!this.isStoredInDB || !this.restclient || !this.radarUID) {
      return;
    }
    const copyObj = this.radarFrame.clone();
    if (this.flipCoordSystem) {
      this.togglePoseYupYdown(copyObj);
    }
    const payload = {
      sensor_id: this.radarUID,
      name: this.name,
      scene: this.sceneID,
      transform_type: "euler",
      translation: [...copyObj.position],
      rotation: [
        THREE.MathUtils.radToDeg(copyObj.rotation.x),
        THREE.MathUtils.radToDeg(copyObj.rotation.y),
        THREE.MathUtils.radToDeg(copyObj.rotation.z),
      ],
      scale: [1.0, 1.0, 1.0],
    };
    const response = await this.restclient.updateRadar(this.radarUID, payload);
    if (response.statusCode === SUCCESS) {
      this.toast?.showToast(`Saved pose for radar ${this.name}.`, "success");
      if (this.saveControl) {
        this.saveControl.domElement.classList.add("disabled");
      }
    } else {
      this.toast?.showToast(
        `Failed to save radar ${this.name}: ${response.errors || "error"}`,
        "danger",
      );
    }
  }
}
