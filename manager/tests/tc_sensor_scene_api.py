#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from http import HTTPStatus

TEST_NAME = "NEX-T10396-API"

def test_sensor_scene_api(rest, result_recorder):
  sensor_id = "test_sensor"
  sensor_name = "Sensor_0"

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
  logging.info(
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
  logging.info("Sensor area verified and confirmed as orphaned (no scene linkage).")

  # Cleanup
  res = rest.deleteSensor(sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
  logging.info("Sensor deleted successfully.")

  result_recorder.success()
