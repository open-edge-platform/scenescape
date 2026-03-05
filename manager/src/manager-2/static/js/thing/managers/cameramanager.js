// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import ThingManager from "/static/js/thing/managers/thingmanager.js";

export default class CameraManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, "camera");
    this.currentCameras = [];
    this.sceneCameras = this.sceneThings;
  }

  refresh(client, topic) {
    this.restclient.getCameras({ scene: this.sceneID }).then((res) => {
      if (res.statusCode == 200) {
        for (const cam of res.content.results) {
          client.publish(topic + cam.uid, "getimage");
        }
      }
    });
  }
}
