#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import random
from tests.utils.log import get_logger
from http import HTTPStatus
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T21886"

def test_sensor_location_api(rest, scene_uid, result_recorder, demo_scene):
  # Create a polygon sensor
  poly_sensor_name = "Sensor_Poly"
  initial_points = ((-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5))
  poly_sensor_data = {
    "name": poly_sensor_name,
    "scene": scene_uid,
    "sensor_id": poly_sensor_name,
    "area": "poly",
    "points": initial_points
  }
  log.info(f"Create polygon payload:", poly_sensor_data)
  res = rest.createSensor(poly_sensor_data)
  assert res, (res.statusCode, res.errors)
  poly_sensor_uid = res['uid']
  assert poly_sensor_uid, "Polygon sensor UID not returned"

  # Update polygon points (shift all points by +0.5 in x and y)
  updated_points = [[x + 0.5, y + 0.5] for x, y in initial_points]
  update_poly_data = {
    "area": "poly",
    "points": updated_points
  }
  log.info(f"Update polygon payload:", update_poly_data)
  res = rest.updateSensor(poly_sensor_uid, update_poly_data)
  assert res.statusCode == HTTPStatus.OK, f"Failed to update polygon sensor: {res.errors}"
  log.info("Polygon sensor points updated.")

  # Verify polygon update
  res = rest.getSensor(poly_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve polygon sensor: {res.errors}"
  points = res['points']
  assert points == updated_points, \
    f"Polygon points did not persist. Expected {updated_points}, got {points}"
  log.info("Polygon sensor points change verified.")

  # Delete the polygon sensor
  res = rest.deleteSensor(poly_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to delete polygon sensor: {res.errors}"
  log.info("Polygon sensor deleted successfully.")

  # Create a circle sensor
  circle_sensor_name = "Sensor_Circle"
  initial_center = [0, 0]
  radius = 1
  circle_sensor_data = {
    "name": circle_sensor_name,
    "scene": scene_uid,
    "sensor_id": circle_sensor_name,
    "area": "circle",
    "center": initial_center,
    "radius": radius
  }
  log.info(f"Create payload:", circle_sensor_data)
  res = rest.createSensor(circle_sensor_data)
  assert res, (res.statusCode, res.errors)
  circle_sensor_uid = res['uid']
  assert circle_sensor_uid, "Sensor UID not returned"

  # Update the circle center
  new_x = initial_center[0] + random.uniform(0.1, 1.0)
  new_y = initial_center[1] + random.uniform(0.1, 1.0)
  updated_center = [new_x, new_y]
  update_circle_data = {
    "area": "circle",
    "center": updated_center,
    "radius": radius
  }
  log.info(f"Update payload:", update_circle_data)
  res = rest.updateSensor(circle_sensor_uid, update_circle_data)
  assert res.statusCode == HTTPStatus.OK, f"Failed to update sensor center: {res.errors}"

  # Verify if circle location has been updated
  res = rest.getSensor(circle_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve sensor: {res.errors}"
  center = res['center']
  assert center == updated_center, \
    f"Sensor center did not persist. Expected {updated_center}, got {center}"
  log.info("Sensor center change verified.")

  # Delete the circle sensor
  res = rest.deleteSensor(circle_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
  log.info("Circle sensor deleted successfully.")

  result_recorder.success()
