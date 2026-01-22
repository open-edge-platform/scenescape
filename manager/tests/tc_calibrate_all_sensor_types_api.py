#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import time

TEST_NAME = "NEX-T10457-API"

class CalibrateAllSensorTypesTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def runTest(self):
    # Get scene UID
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    assert scenes and len(scenes) > 0, f"Scene '{self.sceneName}' not found"
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
      res = self.rest.createSensor(payload)
      assert res.statusCode == HTTPStatus.CREATED, f"Failed to create sensor {sensor['name']}: {res.errors}"
      time.sleep(1)

    print("Successfully calibrated all sensor types.")
    return True

def test_calibrate_all_sensor_types_api(request, record_xml_attribute):
  test = CalibrateAllSensorTypesTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
