// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import * as THREE from '/static/assets/three.module.js';
import { TransformControls } from '/static/examples/jsm/controls/TransformControls.js';

const axes = Array('X', 'Y', 'Z');
let thingTransformControls = {
  addDragControls(camera, orbitControls, dragChangedCallback = () => { }) {
    const controllers = this.controlsFolder.controllersRecursive();

    this.controllersDict = {};
    controllers.forEach((item) => this.controllersDict[item.property] = item);
    const control = new TransformControls(camera, this.renderer.domElement);
    control.name = this.name + '-transform-controls';
    control.size = 0.6;
    control.addEventListener('objectChange', (function () {
      this.setPose(control.mode);
    }).bind(this));

    control.addEventListener('dragging-changed', (function (event) {
      dragChangedCallback();
      orbitControls.enabled = !event.value;
      this.updateSaveButton();
    }).bind(this));

    control.attach(this.transformObject);
    control.setMode('rotate');
    this.transformControl = control;
    this.scene.add(this.getTransformControlObject3D());
    this.setTransformControlVisibility(false);
  },
  addPoseControls(panelSettings) {
    let copyObj = this.transformObject ? this.transformObject.clone() : null;
    let position = copyObj ? copyObj.position : { 'x': '', 'y': '', 'z': '' };
    if (this.flipCoordSystem) this.togglePoseYupYdown(copyObj); //convert yup to ydown
    let rotation = copyObj ? copyObj.rotation : { 'x': '', 'y': '', 'z': '' };

    panelSettings = Object.assign(panelSettings, {
      'toggle rotate/translate': true,
      'pos X': position.x,
      'pos Y': position.y,
      'pos Z': position.z,
      'rot X': THREE.MathUtils.radToDeg(rotation.x),
      'rot Y': THREE.MathUtils.radToDeg(rotation.y),
      'rot Z': THREE.MathUtils.radToDeg(rotation.z),
    });
    let control = this.controlsFolder.add(panelSettings, 'toggle rotate/translate').onChange((function (rotate) {
      this.transformControl.setMode(rotate ? 'rotate' : 'translate');
    }).bind(this));
    control.$widget.firstChild.id = this.name.concat('-', 'toggle-rotate-translate');
    control.$input.classList.add('lil-gui-toggle-image');

    this.poseFolder = this.controlsFolder.addFolder('Pose');
    this.poseFolder.$title.setAttribute('id', this.name + '-transform');

    for (const axis of axes) {
      const name = 'pos ' + axis;
      control = this.poseFolder.add(panelSettings, name).onFinishChange((function (value) {
        this.setAxisPose('translate', axis, value);
      }).bind(this));
      control.$input.id = this.name + '-' + 'pos' + axis;
    }

    for (const axis of axes) {
      const name = 'rot ' + axis;
      control = this.poseFolder.add(panelSettings, name).onFinishChange((function (value) {
        this.setAxisPose('rotate', axis, value);
      }).bind(this));
      control.$input.id = this.name + '-' + 'rot' + axis;
    }
    this.poseFolder.close();
    return control;
  },
  togglePoseYupYdown(object) {
    object.rotateY(Math.PI);
    object.rotateZ(Math.PI);
  },
  resetTransformObject() {
    this.transformControl.detach();
    this.transformControl.attach(this.transformObject);
  },
  setTransformControlVisibility(enable) {
    const object = this.getTransformControlObject3D()
    object.visible = object.enabled = enable;
  },
  toggleTransformControl() {
    const object = this.getTransformControlObject3D();
    object.visible = object.enabled = !object.visible;
  },
  getTransformControlObject3D() {
    return this.transformControl.isObject3D ? this.transformControl: this.transformControl.getHelper();
  },
  setPose(mode, render = true) {
    if (this.transformObject === undefined) {
      return;
    }

    let copyObj = this.transformObject.clone();
    if (this.flipCoordSystem) this.togglePoseYupYdown(copyObj); //convert yup to ydown
    let vec;
    let prefix;
    if (mode === 'translate') {
      vec = copyObj.position;
      prefix = 'pos ';
      for (const axis of axes) {
        const name = prefix + axis;
        this.controllersDict[name].setValue(vec[axis.toLowerCase()]);
      }
    } else if (mode === 'rotate') {
      vec = copyObj.rotation;
      prefix = 'rot ';
      for (const axis of axes) {
        const name = prefix + axis;
        this.controllersDict[name].setValue(THREE.MathUtils.radToDeg(vec[axis.toLowerCase()]));
      }
    }

    if (render) {
      if (typeof this.setPoseSuffix !== "undefined") this.setPoseSuffix();
    }
  },
  setAxisPose(mode, id, value) {
    if (mode === 'rotate') {
      let rotation = new THREE.Vector3();
      for (const axis of axes) {
        rotation[axis.toLowerCase()] = THREE.MathUtils.degToRad(this.controllersDict['rot ' + axis].getValue());
      }
      rotation[id.toLowerCase()] = THREE.MathUtils.degToRad(value);
      this.transformObject.rotation.setFromVector3(rotation);
      if (this.flipCoordSystem) this.togglePoseYupYdown(this.transformObject); // convert to yup
    } else if (mode === 'translate') {
      this.transformObject.position[id.toLowerCase()] = value;
    }
    this.updateSaveButton();
    if (typeof this.setPoseSuffix !== "undefined") this.setPoseSuffix();
  },
  setRotation(rotation, render = true) {
    this.transformObject.rotation.copy(rotation);
    this.setPose('rotate', render);
    this.updateSaveButton();
  },
  setQuaternion(quat, render = true, ydown = false) {
    const quaternion = new THREE.Quaternion(...quat);
    this.transformObject.setRotationFromQuaternion(quaternion);
    if (ydown) this.togglePoseYupYdown(this.transformObject);
    this.setRotation(this.transformObject.rotation, render);
  },
  setPosition(position, render = true) {
    this.transformObject.position.copy(position);
    this.setPose('translate', render);
    this.updateSaveButton();
  }
};

export default thingTransformControls;
