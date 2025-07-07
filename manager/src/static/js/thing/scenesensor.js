// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import SceneRegion from "/static/js/thing/sceneregion.js";

export default class SceneSensor extends SceneRegion {
  constructor(params) {
    if ("area" in params) {
      super(params);
    }
  }
}
