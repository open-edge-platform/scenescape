#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10396-API"

class SensorSceneAreaTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

    self.scene_name = self.params["scene"]
    scenes = self.rest.getScenes({"name": self.scene_name})["results"]
    assert scenes and len(scenes) > 0, f"Scene '{self.scene_name}' not found"
    self.scene_uid = scenes[0]["uid"]

  def runTest(self):
    sensor_id = "test_sensor"
    sensor_name = "Sensor_0"

    # Attempt to create sensor with area='scene' but missing 'scene' field (should succeed)
    sensor_data_missing_scene = {
      "sensor_id": sensor_id,
      "name": sensor_name,
      "area": "scene",
    }
    res = self.rest.createSensor(sensor_data_missing_scene)
    assert res.statusCode in (
      HTTPStatus.OK,
      HTTPStatus.CREATED,
    ), f"Expected success, got {res.statusCode}. Sensor creation without 'scene' should be allowed."
    sensor_uid = res["uid"]
    assert sensor_uid, "Sensor UID not returned"
    print(
      "Sensor successfully created with area 'scene' and no scene assigned (orphaned sensor)."
    )

    # Verify sensor details
    res = self.rest.getSensor(sensor_uid)
    assert (
      res.statusCode == HTTPStatus.OK
    ), f"Failed to retrieve sensor: {res.errors}"
    assert (
      res["area"] == "scene"
    ), f"Sensor area mismatch: expected 'scene', got '{res['area']}'"
    assert not res.get(
      "scene"
    ), f"Expected no scene linkage, but got '{res.get('scene')}'"
    print("Sensor area verified and confirmed as orphaned (no scene linkage).")

    # Cleanup
    res = self.rest.deleteSensor(sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
    print("Sensor deleted successfully.")

    return True

def test_sensor_scene_area_api(request, record_xml_attribute):
  test = SensorSceneAreaTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
