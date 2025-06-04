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

import ThingManager from '/static/js/thing/managers/thingmanager.js';

export default class CameraManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, 'camera');
    this.currentCameras = [];
    this.sceneCameras = this.sceneThings;
  }

  refresh(client, topic) {
    this.restclient.getCameras({ scene: this.sceneID }).then((res) => {
      if (res.statusCode == 200) {
        for (const cam of res.content.results) {
          client.publish(topic + cam.uid, 'getimage')
        }
      }
    });
  }
}
