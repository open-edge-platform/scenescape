#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10457-API"

def test_calibrate_all_sensor_types_api(params, record_xml_attribute):
    record_xml_attribute("name", TEST_NAME)
    exit_code = 1

    rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
    assert rest.authenticate(params['user'], params['password'])

    scenes = rest.getScenes({'name': params['scene_name']})['results']
    assert scenes, f"Scene '{params['scene_name']}' not found"
    scene_uid = scenes[0]['uid']

    # Create sensors of different types
    sensor_types = [
      # Entire scene sensor
      {"name": "sensor_entire_scene", "area": "scene"},
      # Circle sensor
      {"name": "sensor_circle", "area": "circle", "radius": 10, "center": [5, 5]},
      # Polygon sensor
      {"name": "sensor_triangle", "area": "poly", "points": [[0,0],[10,0],[5,10]]},
    ]

    try:
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
        time.sleep(1)

      print("Successfully calibrated all sensor types.")
      exit_code = 0
    finally:
      record_test_result(TEST_NAME, exit_code)
