// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import ThingManager from "/static/js/thing/managers/thingmanager.js";

export default class RegionManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, "region");
    this.sceneRegions = this.sceneThings;
  }
}
