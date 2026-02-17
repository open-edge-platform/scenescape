#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10396-API"

def test_sensor_scene_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  scenes = rest.getScenes({'name': params['scene_name']})['results']
  assert scenes, f"Scene '{params['scene_name']}' not found"

  sensor_id = "test_sensor"
  sensor_name = "Sensor_0"

  try:
    # Attempt to create sensor with area='scene' but missing 'scene' field (should succeed)
    sensor_data_missing_scene = {
      "sensor_id": sensor_id,
      "name": sensor_name,
      "area": "scene",
    }
    res = rest.createSensor(sensor_data_missing_scene)
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
    res = rest.getSensor(sensor_uid)
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
    res = rest.deleteSensor(sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
    print("Sensor deleted successfully.")

    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
