// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

"use strict";

import ThingManager from "/static/js/thing/managers/thingmanager.js";

export default class RadarManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, "radar");
    this.sceneRadars = this.sceneThings;
  }
}
