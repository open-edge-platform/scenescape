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

  async load(params) {
    await this.syncWithDatabase(params, null, null, false);
  }

  async getAllCameras() {
    const cameras = [];
    let page = 1;
    let response;
    do {
      response = await this.restclient.getCameras({
        scene: this.sceneID,
        page,
      });
      if (response.statusCode !== 200) {
        console.error("Failed to fetch camera page", page, response.statusCode);
        return response;
      }
      cameras.push(...response.content.results);
      page += 1;
    } while (response.content.next);
    return { ...response, content: { ...response.content, results: cameras } };
  }

  refresh(client, topic) {
    this.getAllCameras().then((res) => {
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
    const res = await this.getAllCameras();
    if (generation !== this.syncGeneration) return { added: [], removed: [] };
    if (res.statusCode !== 200) return { added: [], removed: [] };
    const inDB = new Map(res.content.results.map((cam) => [cam.uid, cam]));
    const renamedKeys = Object.entries(this.sceneCameras).filter(
      ([key, camera]) =>
        key !== "undefined" &&
        camera?.isStoredInDB &&
        camera.cameraUID &&
        key !== camera.cameraUID,
    );
    for (const [key] of renamedKeys) delete this.sceneCameras[key];
    for (const [, camera] of renamedKeys)
      this.sceneCameras[camera.cameraUID] = camera;

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
        this.sceneCameras[uid].syncPosePolicy(thing);
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
      if (
        sceneCamera &&
        sceneCamera.posePolicy !== "configured" &&
        camera.pose_policy !== "configured"
      )
        sceneCamera.updatePose(camera);
    }
  }
}
