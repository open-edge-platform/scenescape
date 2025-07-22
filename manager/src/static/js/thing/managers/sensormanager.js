// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import ThingManager from "/static/js/thing/managers/thingmanager.js";

export default class SensorManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, "sensor");
    this.sceneSensors = this.sceneThings;
  }
}
