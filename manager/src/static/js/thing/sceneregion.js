// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import ThingControls from "/static/js/thing/controls/thingcontrols.js";
import * as THREE from "/static/assets/three.module.js";
import validateInputControls from "/static/js/thing/controls/validateinputcontrols.js";

const MAX_OPACITY = 1;
const MAX_SEGMENTS = 65;

export default class SceneRegion extends THREE.Object3D {
  constructor(params) {
    super();
    this.name = params.name;
    this.region = params;
    this.points = [];
    this.isStaff = params.isStaff;
    this.height = params.height;
    this.buffer_size = params.buffer_size;
    this.regionType = null;

    if (this.region.area === "scene") {
      this.region["points"] = [];
      this.regionType = "scene";
    } else if (this.region.area === "circle") {
      this.regionType = "circle";
    } else {
      this.regionType = "poly";
    }
  }

  createShape() {
    this.extrudeSettings = {
      depth: this.height,
      bevelEnabled: false,
    };
    this.setOpacity = true;
    this.material = new THREE.MeshLambertMaterial({
      color: this.color,
      transparent: true,
      opacity: this.opacity,
    });
    this.scaleFactor = this.height;
    this.setPoints();

    if (this.regionType === "poly") {
      if (this.buffer_size && this.buffer_size > 0) {
        const inflatedGeometry = this.createPoly(this.createInflatedMesh);
        let inflatedMaterial = new THREE.MeshLambertMaterial({
          color: this.color,
          transparent: true,
          opacity: this.opacity / 2,
        });
        this.inflatedShape = new THREE.Mesh(inflatedGeometry, inflatedMaterial);
      }

      const polyGeometry = this.createPoly((points) => new THREE.Shape(points));
      this.shape = new THREE.Mesh(polyGeometry, this.material);
    } else if (this.regionType === "circle") {
      let cylinderGeometry = null;
      if (this.region.hasOwnProperty("center")) {
        cylinderGeometry = this.createCircle(
          this.region.center[0],
          this.region.center[1],
        );
      } else {
        cylinderGeometry = this.createCircle(this.region.x, this.region.y);
      }
      this.shape = new THREE.Mesh(cylinderGeometry, this.material);
    }
    // Set render order to ensure regions are rendered before blocks
    this.shape.renderOrder = 1;
    this.type = "region";
  }

  setPoints() {
    if (this.region === null) {
      throw new Error("Region is invalid");
    }

    if (this.regionType === "poly") {
      this.region.points.forEach((p) => {
        p.push(0);
        this.points.push(new THREE.Vector3(...p));
      });
    }
    if (this.regionType === "circle") {
      for (let i = 0; i <= MAX_SEGMENTS; i++) {
        const theta = (i / MAX_SEGMENTS) * Math.PI * 2;
        const x = this.region.radius * Math.cos(theta);
        const y = this.region.radius * Math.sin(theta);
        this.points.push(new THREE.Vector2(x, y));
      }
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

  createPoly(createBasePolygon) {
    let polyGeometry = null;
    if (this.points.length > 0) {
      // Create shape from points, with optional buffer
      const points2D = this.points.map((p) => new THREE.Vector2(p.x, p.y));
      let shape = createBasePolygon(points2D);
      polyGeometry = new THREE.ExtrudeGeometry(shape, this.extrudeSettings);
    }
    return polyGeometry;
  }

  createInflatedMesh = (polygonPoints) => {
    const inflatedPoints = [];
    const pointCount = polygonPoints.length;

    // Determine if polygon is clockwise or counterclockwise
    let area = 0;
    for (let i = 0; i < pointCount; i++) {
      const j = (i + 1) % pointCount;
      area += polygonPoints[i].x * polygonPoints[j].y;
      area -= polygonPoints[j].x * polygonPoints[i].y;
    }
    const isClockwise = area < 0;
    // Reverse sign to inflate instead of deflate
    const sign = isClockwise ? 1 : -1;

    for (let i = 0; i < pointCount; i++) {
      // Get the current, previous, and next points
      const prevPoint = polygonPoints[(i - 1 + pointCount) % pointCount];
      const currentPoint = polygonPoints[i];
      const nextPoint = polygonPoints[(i + 1) % pointCount];

      // Calculate edge vectors
      const v1 = new THREE.Vector2()
        .subVectors(currentPoint, prevPoint)
        .normalize();
      const v2 = new THREE.Vector2()
        .subVectors(nextPoint, currentPoint)
        .normalize();

      // Calculate perpendicular vectors (normals) pointing outward
      const normal1 = new THREE.Vector2(-v1.y * sign, v1.x * sign);
      const normal2 = new THREE.Vector2(-v2.y * sign, v2.x * sign);

      // Calculate the cross product to determine if the corner is convex or concave
      const crossProduct = v1.x * v2.y - v1.y * v2.x;
      const isConvex = crossProduct * sign < 0;

      // Calculate the offset direction
      let offsetVector;
      if (isConvex) {
        // For convex corners, use the miter vector (average of normals)
        offsetVector = new THREE.Vector2()
          .addVectors(normal1, normal2)
          .normalize();
        // Calculate the miter length to maintain constant offset distance
        const miterLength =
          this.buffer_size / Math.max(0.1, offsetVector.dot(normal1));
        offsetVector.multiplyScalar(miterLength);
      } else {
        // For concave corners, use a beveled approach with separate offsets
        offsetVector = new THREE.Vector2()
          .addVectors(
            normal1.clone().multiplyScalar(this.buffer_size),
            normal2.clone().multiplyScalar(this.buffer_size),
          )
          .multiplyScalar(0.5);
      }

      // Calculate the new inflated point
      const newPoint = new THREE.Vector2().addVectors(
        currentPoint,
        offsetVector,
      );
      inflatedPoints.push(newPoint);
    }

    // 5. Create the Three.js shape and extrude it 🧊
    const inflatedShape = new THREE.Shape(inflatedPoints);
    return inflatedShape;
  };

  changeGeometry(geometry) {
    if (this.hasOwnProperty("shape") && this.shape !== null) {
      this.shape.geometry.dispose();
      this.shape.geometry = geometry;
    } else {
      this.shape = new THREE.Mesh(geometry, this.material);
      this.add(this.shape);
    }
  }

  addObject(params) {
    this.color = params.color;
    this.drawObj = params.drawObj;
    this.opacity = params.opacity;
    this.maxOpacity = MAX_OPACITY;
    this.scene = params.scene;
    this.regionsFolder = params.regionsFolder;
    this.visible = false;
    this.regionControls = new ThingControls(this);

    Object.assign(this, validateInputControls);
    this.regionControls.addArea();
    if (this.points && this.points.length > 0) {
      let x = this.points[0].x;
      let y = this.points[1].y;
      if (this.regionType === "circle") {
        if (this.region.hasOwnProperty("center")) {
          x = this.region.center[0];
          y = this.region.center[1];
        } else {
          x = this.region.x;
          y = this.region.y;
        }
      }

      this.textPos = {
        x: x,
        y: y,
        z: this.height,
      };
      this.drawObj
        .createTextObject(this.name, this.textPos)
        .then((textMesh) => {
          this.add(textMesh);
        });
    }
    this.regionControls.addToScene();
    this.regionControls.addControlPanel(this.regionsFolder);
    this.controlsFolder = this.regionControls.controlsFolder;
    this.disableFields(["name"]);

    if (this.isStaff === null) {
      let fields = Object.keys(this.regionControls.panelSettings);
      this.disableFields(fields);
      this.executeOnControl("opacity", (control) => {
        control[0].domElement.classList.add("disabled");
      });
    }
  }

  createGeometry(data) {
    this.region = data;
    let geometry = null;
    if (data.area === "circle") {
      this.regionType = "circle";
      this.setPoints();
      geometry = this.createCircle(data.x, data.y);
      this.changeGeometry(geometry);
    } else if (data.area === "poly") {
      this.regionType = "poly";
      this.setPoints();
      geometry = this.createPoly();
      this.changeGeometry(geometry);
    } else {
      this.remove(this.shape);
      this.shape = null;
    }
  }

  updateShape(data) {
    this.regionControls.updateGeometry(data);
  }
}
