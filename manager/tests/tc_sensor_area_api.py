#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10401-API"

def test_sensor_area_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  scenes = rest.getScenes({'name': params['scene_name']})['results']
  assert scenes, f"Scene '{params['scene_name']}' not found"
  scene_uid = scenes[0]['uid']

  sensor_name_poly = "Sensor_Poly"
  sensor_name_circle = "Sensor_Circle"

  try:
    # Create a polygon sensor
    initial_poly_points = [[-0.5, 0.5], [0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]]
    poly_sensor_data = {
      "name": sensor_name_poly,
      "scene": scene_uid,
      "sensor_id": sensor_name_poly,
      "area": "poly",
      "points": initial_poly_points
    }
    print("\nCreate polygon payload:", poly_sensor_data)
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
    print("Update polygon payload:", update_data_poly)
    res = rest.updateSensor(poly_sensor_uid, update_data_poly)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update polygon area: {res.errors}"
    print("Polygon sensor points updated.")

    # Verify if polygon area has been updated
    res = rest.getSensor(poly_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve polygon sensor: {res.errors}"
    assert res['points'] == updated_poly_points, f"Polygon points mismatch: expected {updated_poly_points}, got {res['points']}"
    print("Polygon area change verified.")

    # Delete the polygon sensor
    res = rest.deleteSensor(poly_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete polygon sensor: {res.errors}"
    print("Polygon sensor deleted successfully.")

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
    print("Create payload:", circle_sensor_data)
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
    print("Update payload:", update_circle_data)
    res = rest.updateSensor(circle_sensor_uid, update_circle_data)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update circle area: {res.errors}"

    # Verify if circle area has been updated
    res = rest.getSensor(circle_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve circle sensor: {res.errors}"
    assert res['radius'] == updated_radius, f"Circle radius mismatch: expected {updated_radius}, got {res['radius']}"
    print("Circle area change verified.")

    # Delete the circle sensor
    res = rest.deleteSensor(circle_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
    print("Circle sensor deleted successfully.")

    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
