#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import random
from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import tests.common_test_utils as common

TEST_NAME = "NEX-T10400-API"

class SensorLocationTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.sceneName = self.params['scene']
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    assert scenes and len(scenes) > 0, f"Scene '{self.sceneName}' not found"
    self.scene_uid = scenes[0]['uid']
    self.sensor_name = "Sensor_Circle"

  def runTest(self):
    # Create a polygon sensor
    poly_sensor_name = "Sensor_Poly"
    initial_points = ((-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5))
    poly_sensor_data = {
      "name": poly_sensor_name,
      "scene": self.scene_uid,
      "sensor_id": poly_sensor_name,
      "area": "poly",
      "points": initial_points
    }
    print("\nCreate polygon payload:", poly_sensor_data)
    res = self.rest.createSensor(poly_sensor_data)
    assert res, (res.statusCode, res.errors)
    poly_sensor_uid = res['uid']
    assert poly_sensor_uid, "Polygon sensor UID not returned"

    # Update polygon points (shift all points by +0.5 in x and y)
    updated_points = [[x + 0.5, y + 0.5] for x, y in initial_points]
    update_poly_data = {
      "area": "poly",
      "points": updated_points
    }
    print("Update polygon payload:", update_poly_data)
    res = self.rest.updateSensor(poly_sensor_uid, update_poly_data)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update polygon sensor: {res.errors}"
    print("Polygon sensor points updated.")

    # Verify polygon update
    res = self.rest.getSensor(poly_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve polygon sensor: {res.errors}"
    points = res['points']
    assert points == updated_points, \
      f"Polygon points did not persist. Expected {updated_points}, got {points}"
    print("Polygon sensor points change verified.")

    # Delete the polygon sensor
    res = self.rest.deleteSensor(poly_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete polygon sensor: {res.errors}"
    print("Polygon sensor deleted successfully.")

    # Create a circle sensor
    circle_sensor_name = "Sensor_Circle"
    initial_center = [0, 0]
    radius = 1
    circle_sensor_data = {
      "name": circle_sensor_name,
      "scene": self.scene_uid,
      "sensor_id": circle_sensor_name,
      "area": "circle",
      "center": initial_center,
      "radius": radius
    }
    print("Create payload:", circle_sensor_data)
    res = self.rest.createSensor(circle_sensor_data)
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
    print("Update payload:", update_circle_data)
    res = self.rest.updateSensor(circle_sensor_uid, update_circle_data)
    assert res.statusCode == HTTPStatus.OK, f"Failed to update sensor center: {res.errors}"

    # Verify if circle location has been updated
    res = self.rest.getSensor(circle_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve sensor: {res.errors}"
    center = res['center']
    assert center == updated_center, \
      f"Sensor center did not persist. Expected {updated_center}, got {center}"
    print("Sensor center change verified.")

    # Delete the circle sensor
    res = self.rest.deleteSensor(circle_sensor_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete sensor: {res.errors}"
    print("Circle sensor deleted successfully.")

    return True

def test_sensor_location_main_api(request, record_xml_attribute):
  test = SensorLocationTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
