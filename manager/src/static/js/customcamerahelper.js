// Copyright (C) 2023 Intel Corporation
//
// This software and the related documents are Intel copyrighted materials,
// and your use of them is governed by the express license under which they
// were provided to you ("License"). Unless the License provides otherwise,
// you may not use, modify, copy, publish, distribute, disclose or transmit
// this software or the related documents without Intel's prior written permission.
//
// This software and the related documents are provided as is, with no express
// or implied warranties, other than those that are expressly stated in the License.

import * as THREE from '/static/assets/three.module.js';

const _vector = new THREE.Vector3();
let _camera;

const FAR = 1.0;
const NEAR = 0.2;
export default class CustomCameraHelper extends THREE.CameraHelper {

  constructor(camera) {
    super(camera);
  }

  update() {
    const geometry = this.geometry;
    const pointMap = this.pointMap;

    const w = 1, h = 1;

    // we need just camera projection matrix inverse
    // world matrix must be identity

    _camera = this.camera.clone();
    _camera.far = FAR;
    _camera.near = NEAR;
    _camera.updateProjectionMatrix();

    // center / target

    setPoint('c', pointMap, geometry, _camera, 0, 0, - 1);
    setPoint('t', pointMap, geometry, _camera, 0, 0, 1);

    // near

    setPoint('n1', pointMap, geometry, _camera, - w, - h, - 1);
    setPoint('n2', pointMap, geometry, _camera, w, - h, - 1);
    setPoint('n3', pointMap, geometry, _camera, - w, h, - 1);
    setPoint('n4', pointMap, geometry, _camera, w, h, - 1);

    // far

    setPoint('f1', pointMap, geometry, _camera, - w, - h, 1);
    setPoint('f2', pointMap, geometry, _camera, w, - h, 1);
    setPoint('f3', pointMap, geometry, _camera, - w, h, 1);
    setPoint('f4', pointMap, geometry, _camera, w, h, 1);

    // up

    setPoint('u1', pointMap, geometry, _camera, w * 0.7, h * 1.1, - 1);
    setPoint('u2', pointMap, geometry, _camera, - w * 0.7, h * 1.1, - 1);
    setPoint('u3', pointMap, geometry, _camera, 0, h * 2, - 1);

    // cross

    setPoint('cf1', pointMap, geometry, _camera, - w, 0, 1);
    setPoint('cf2', pointMap, geometry, _camera, w, 0, 1);
    setPoint('cf3', pointMap, geometry, _camera, 0, - h, 1);
    setPoint('cf4', pointMap, geometry, _camera, 0, h, 1);

    setPoint('cn1', pointMap, geometry, _camera, - w, 0, - 1);
    setPoint('cn2', pointMap, geometry, _camera, w, 0, - 1);
    setPoint('cn3', pointMap, geometry, _camera, 0, - h, - 1);
    setPoint('cn4', pointMap, geometry, _camera, 0, h, - 1);

    geometry.getAttribute('position').needsUpdate = true;
  }

};

function setPoint(point, pointMap, geometry, camera, x, y, z) {

  _vector.set(x, y, z).unproject(camera);

  const points = pointMap[point];

  if (points !== undefined) {

    const position = geometry.getAttribute('position');

    for (let i = 0, l = points.length; i < l; i++) {

      position.setXYZ(points[i], _vector.x, _vector.y, _vector.z);

    }

  }

}
