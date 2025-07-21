// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import ThingManager from "/static/js/thing/managers/thingmanager.js";

export default class TripwireManager extends ThingManager {
  constructor(sceneID) {
    super(sceneID, "tripwire");
    this.sceneTripwires = this.sceneThings;
  }
}
