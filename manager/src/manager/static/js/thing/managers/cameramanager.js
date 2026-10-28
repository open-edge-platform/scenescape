// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import ThingManager from "/static/js/thing/managers/thingmanager.js";

export default class CameraManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, "camera");
    this.currentCameras = [];
    this.sceneCameras = this.sceneThings;
    this.syncGeneration = 0;
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

  // Reconcile with the database after a CMD_DATABASE notice: build cameras
  // that appeared (e.g. a handheld registering itself), tear down cameras
  // that were deleted elsewhere, leave the rest untouched so in-progress
  // pose edits survive. Refresh optics only when their persisted values change.
  // Returns { added, removed } uids.
  async syncWithDatabase(params, client, appName, isVARunning) {
    const generation = ++this.syncGeneration;
    const res = await this.restclient.getCameras({ scene: this.sceneID });
    if (generation !== this.syncGeneration) return { added: [], removed: [] };
    if (res.statusCode !== 200) return { added: [], removed: [] };
    const inDB = new Map(res.content.results.map((cam) => [cam.uid, cam]));

    const removed = [];
    for (const uid of Object.keys(this.sceneCameras)) {
      if (uid === "undefined" || inDB.has(uid)) continue;
      const cam = this.sceneCameras[uid];
      if (cam && cam.isStoredInDB) {
        cam.detach(params.camerasFolder);
        delete this.sceneCameras[uid];
        removed.push(uid);
      }
    }

    const added = [];
    for (const [uid, thing] of inDB) {
      if (uid in this.sceneCameras) {
        this.sceneCameras[uid].syncOptics(thing);
        continue;
      }
      thing.isStoredInDB = true;
      const cam = this.add(thing);
      cam.toast = params.toast;
      params.currentThings = this.sceneCameras;
      cam.addObject(params);
      if (client) {
        cam.setMQTTClient(client, appName);
        cam.setVARunning(isVARunning);
      }
      added.push(uid);
    }
    return { added, removed };
  }

  updatePoses(cameras) {
    if (!Array.isArray(cameras)) return;
    for (const camera of cameras) {
      if (camera.dynamic_pose !== true) continue;
      const sceneCamera = this.sceneCameras[camera.id];
      if (sceneCamera) sceneCamera.updatePose(camera);
    }
  }
}
