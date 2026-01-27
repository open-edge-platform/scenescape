#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import random
from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10401-API"

class SensorAreaTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.sceneName = self.params['scene']
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    assert scenes and len(scenes) > 0, f"Scene '{self.sceneName}' not found"
    self.scene_uid = scenes[0]['uid']
    self.sensor_name_poly = "Sensor_Poly"
    self.sensor_name_circle = "Sensor_Circle"

  def runTest(self):
    # Create a polygon sensor
    initial_poly_points = [[-0.5, 0.5], [0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]]
    poly_sensor_data = {
      "name": self.sensor_name_poly,
      "scene": self.scene_uid,
      "sensor_id": self.sensor_name_poly,
      "area": "poly",
      "points": initial_poly_points
    }
    print("\nCreate polygon payload:", poly_sensor_data)
    res = self.rest.createSensor(poly_sensor_data)
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
    res = self.rest.updateSensor(poly_sensor_uid, update_data_poly)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update polygon area: {res.errors}"
    print("Polygon sensor points updated.")

    # Verify if polygon area has been updated
    res = self.rest.getSensor(poly_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve polygon sensor: {res.errors}"
    assert res['points'] == updated_poly_points, f"Polygon points mismatch: expected {updated_poly_points}, got {res['points']}"
    print("Polygon area change verified.")

    # Delete the polygon sensor
    res = self.rest.deleteSensor(poly_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete polygon sensor: {res.errors}"
    print("Polygon sensor deleted successfully.")

    # Create a circle sensor
    center = (0, 0)
    initial_radius = 1
    circle_sensor_data = {
      "name": self.sensor_name_circle,
      "scene": self.scene_uid,
      "sensor_id": self.sensor_name_circle,
      "area": "circle",
      "center": center,
      "radius": initial_radius
    }
    print("Create payload:", circle_sensor_data)
    res = self.rest.createSensor(circle_sensor_data)
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
    res = self.rest.updateSensor(circle_sensor_uid, update_circle_data)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update circle area: {res.errors}"

    # Verify if circle area has been updated
    res = self.rest.getSensor(circle_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve circle sensor: {res.errors}"
    assert res['radius'] == updated_radius, f"Circle radius mismatch: expected {updated_radius}, got {res['radius']}"
    print("Circle area change verified.")

    # Delete the circle sensor
    res = self.rest.deleteSensor(circle_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
    print("Circle sensor deleted successfully.")

    return True

def test_sensor_area_main_api(request, record_xml_attribute):
  test = SensorAreaTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
