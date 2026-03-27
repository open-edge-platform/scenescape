#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from http import HTTPStatus

TEST_NAME = "NEX-T10401-API"

def test_sensor_area_api(rest, scene_uid, result_recorder):
  sensor_name_poly = "Sensor_Poly"
  sensor_name_circle = "Sensor_Circle"

  # Create a polygon sensor
  initial_poly_points = [[-0.5, 0.5], [0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]]
  poly_sensor_data = {
    "name": sensor_name_poly,
    "scene": scene_uid,
    "sensor_id": sensor_name_poly,
    "area": "poly",
    "points": initial_poly_points
  }
  logging.info(f"Create polygon payload:", poly_sensor_data)
  res = rest.createSensor(poly_sensor_data)
  assert res, (res.statusCode, res.errors)
  poly_sensor_uid = res['uid']
  assert poly_sensor_uid, "Polygon sensor UID not returned"

  # Update the polygon points
  updated_poly_points = [[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
  update_data_poly = {
    "area": "poly",
    "points": updated_poly_points
  }
  logging.info(f"Update polygon payload:", update_data_poly)
  res = rest.updateSensor(poly_sensor_uid, update_data_poly)
  assert res.statusCode == HTTPStatus.OK, f"Failed to update polygon area: {res.errors}"
  logging.info("Polygon sensor points updated.")

  # Verify if polygon area has been updated
  res = rest.getSensor(poly_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve polygon sensor: {res.errors}"
  assert res['points'] == updated_poly_points, f"Polygon points mismatch: expected {updated_poly_points}, got {res['points']}"
  logging.info("Polygon area change verified.")

  # Delete the polygon sensor
  res = rest.deleteSensor(poly_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to delete polygon sensor: {res.errors}"
  logging.info("Polygon sensor deleted successfully.")

  # Create a circle sensor
  center = (0, 0)
  initial_radius = 1
  circle_sensor_data = {
    "name": sensor_name_circle,
    "scene": scene_uid,
    "sensor_id": sensor_name_circle,
    "area": "circle",
    "center": center,
    "radius": initial_radius
  }
  logging.info(f"Create payload:", circle_sensor_data)
  res = rest.createSensor(circle_sensor_data)
  assert res, (res.statusCode, res.errors)
  circle_sensor_uid = res['uid']
  assert circle_sensor_uid, "Circle sensor UID not returned"

  # Update the circle center and radius
  updated_radius = 1.5
  update_circle_data = {
    "area": "circle",
    "center": center,
    "radius": updated_radius
  }
  logging.info(f"Update payload:", update_circle_data)
  res = rest.updateSensor(circle_sensor_uid, update_circle_data)
  assert res.statusCode == HTTPStatus.OK, f"Failed to update circle area: {res.errors}"

  # Verify if circle area has been updated
  res = rest.getSensor(circle_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve circle sensor: {res.errors}"
  assert res['radius'] == updated_radius, f"Circle radius mismatch: expected {updated_radius}, got {res['radius']}"
  logging.info("Circle area change verified.")

  # Delete the circle sensor
  res = rest.deleteSensor(circle_sensor_uid)
  assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
  logging.info("Circle sensor deleted successfully.")

  result_recorder.success()
