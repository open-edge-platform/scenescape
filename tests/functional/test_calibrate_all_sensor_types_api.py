#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.utils.log import get_logger
from http import HTTPStatus
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T21877"

def test_calibrate_all_sensor_types_api(rest, scene_uid, result_recorder, demo_scene):
  # Create sensors of different types
  sensor_types = [
    # Entire scene sensor
    {"name": "sensor_entire_scene", "area": "scene"},
    # Circle sensor
    {"name": "sensor_circle", "area": "circle", "radius": 10, "center": [5, 5]},
    # Polygon sensor
    {"name": "sensor_triangle", "area": "poly", "points": [[0,0],[10,0],[5,10]]},
  ]

  for sensor in sensor_types:
    payload = {
      "scene": scene_uid,
      "name": sensor["name"],
      "area": sensor["area"]
    }
    if sensor["area"] == "circle":
      payload["radius"] = sensor["radius"]
      payload["center"] = sensor["center"]
    elif sensor["area"] == "poly":
      payload["points"] = sensor["points"]
    res = rest.createSensor(payload)
    assert res.statusCode == HTTPStatus.CREATED, f"Failed to create sensor {sensor['name']}: {res.errors}"
  log.info("Successfully calibrated all sensor types.")

  result_recorder.success()
