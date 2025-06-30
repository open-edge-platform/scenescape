// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

export default class ThingControls {
  constructor(object3D) {
    this.object3D = object3D;
    this.scene = this.object3D.scene;
  }

  addControlPanel(folder) {
    this.controlsFolder = folder.addFolder(this.object3D.name);
    this.panelSettings = {
      name: this.object3D.name,
      color: this.object3D.color,
      show: false,
      height: this.object3D.height,
    };

    let control = this.controlsFolder.add(this.panelSettings, "name");
    let textMesh = this.object3D.scene.getObjectByName(
      "textObject_" + this.object3D.name,
    );

    control = this.controlsFolder
      .add(
        this.panelSettings,
        "height",
        this.object3D.height,
        this.object3D.maxHeight,
      )
      .onChange(
        function (value) {
          if (
            this.object3D.hasOwnProperty("shape") &&
            this.object3D.shape !== null
          ) {
            this.object3D.shape.scale.z = value / this.object3D.scaleFactor;
            let textMesh = this.object3D.scene.getObjectByName(
              "textObject_" + this.object3D.name,
            );
            textMesh.position.z = value;
          }
        }.bind(this),
      );

    if (this.object3D.setOpacity) {
      control = this.controlsFolder
        .add(this.object3D.material, "opacity", 0, this.object3D.maxOpacity)
        .name("opacity");
    }

    control = this.controlsFolder.add(this.panelSettings, "show").onChange(
      function (value) {
        this.object3D.visible = value;
      }.bind(this),
    );

    control = this.controlsFolder
      .addColor(this.panelSettings, "color")
      .onChange(
        function (value) {
          this.object3D.material.color.set(value);
        }.bind(this),
      );
  }

  addArea() {
    this.object3D.createShape();
    if (this.object3D.hasOwnProperty("shape")) {
      this.object3D.add(this.object3D.shape);
    }
  }

  addToScene() {
    this.scene.add(this.object3D);
  }

  updateGeometry(data) {
    this.object3D.points = [];
    this.object3D.createGeometry(data);
    let textObject = this.object3D.scene.getObjectByName(
      "textObject_" + this.object3D.name,
    );
    this.object3D.scene.remove(textObject);
    if (this.object3D.points.length > 0) {
      let x = this.object3D.points[0].x;
      let y = this.object3D.points[1].y;
      if (this.object3D.regionType === "circle") {
        x = data.x;
        y = data.y;
      }
      this.object3D.textPos = {
        x: x,
        y: y,
        z: this.object3D.height,
      };
      this.drawObj
        .createTextObject(this.object3D.name, this.object3D.textPos)
        .then((textMesh) => {
          this.object3D.add(textMesh);
        });
    }
  }
}
