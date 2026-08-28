#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Scene.processRadarData."""

from scene_common.radar import Radar
from scene_common.timestamp import get_iso_time


def test_processRadarData_unknown_radar_returns_false(scene_obj):
  payload = {
    "id": "missing-radar",
    "timestamp": get_iso_time(),
    "objects": {"vehicle": []},
  }
  assert scene_obj.processRadarData(payload) is False


def test_processRadarData_with_pose_returns_true(scene_obj):
  radar = Radar("radar1", {
    "translation": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
  })
  scene_obj.radars["radar1"] = radar
  payload = {
    "id": "radar1",
    "timestamp": get_iso_time(),
    "objects": {
      "vehicle": [
        {
          "id": 1,
          "category": "vehicle",
          "translation": [3.0, 1.0, 0.0],
          "size": [2.0, 1.5, 1.5],
          "confidence": 0.8,
        }
      ]
    },
  }
  assert scene_obj.processRadarData(payload) is True
