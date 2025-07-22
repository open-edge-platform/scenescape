// SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import SceneRegion from "/static/js/thing/sceneregion.js";

export default class SceneSensor extends SceneRegion {
  constructor(params) {
    if ("area" in params) {
      super(params);
    }
  }
}
