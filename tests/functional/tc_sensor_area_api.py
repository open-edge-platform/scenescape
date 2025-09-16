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
        initial_poly_points = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        sensor_data_poly = {
            "name": self.sensor_name_poly,
            "scene": self.scene_uid,
            "sensor_id": self.sensor_name_poly,
            "area": "poly",
            "points": initial_poly_points
        }
        res = self.rest.createSensor(sensor_data_poly)
        assert res, (res.statusCode, res.errors)
        sensor_uid_poly = res['uid']
        assert sensor_uid_poly, "Polygon sensor UID not returned"

        # Update the polygon points
        updated_poly_points = [[50.0, 50.0], [150.0, 50.0], [150.0, 150.0], [50.0, 150.0]]
        update_data_poly = {
            "area": "poly",
            "points": updated_poly_points
        }
        res = self.rest.updateSensor(sensor_uid_poly, update_data_poly)
        assert res.statusCode == HTTPStatus.OK, f"Failed to update polygon area: {res.errors}"

        # Verify if polygon area has been updated
        res = self.rest.getSensor(sensor_uid_poly)
        assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve polygon sensor: {res.errors}"
        assert res['points'] == updated_poly_points, f"Polygon points mismatch: expected {updated_poly_points}, got {res['points']}"
        print("Polygon area change verified.")

        # Create a circle sensor
        initial_center = [200.0, 200.0]
        initial_radius = 75.0
        sensor_data_circle = {
            "name": self.sensor_name_circle,
            "scene": self.scene_uid,
            "sensor_id": self.sensor_name_circle,
            "area": "circle",
            "center": initial_center,
            "radius": initial_radius
        }
        res = self.rest.createSensor(sensor_data_circle)
        assert res, (res.statusCode, res.errors)
        sensor_uid_circle = res['uid']
        assert sensor_uid_circle, "Circle sensor UID not returned"

        # Update the circle center and radius
        updated_center = [250.0, 250.0]
        updated_radius = 100.0
        update_data_circle = {
            "area": "circle",
            "center": updated_center,
            "radius": updated_radius
        }
        res = self.rest.updateSensor(sensor_uid_circle, update_data_circle)
        assert res.statusCode == HTTPStatus.OK, f"Failed to update circle area: {res.errors}"

        # Verify if circle area has been updated
        res = self.rest.getSensor(sensor_uid_circle)
        assert res.statusCode == HTTPStatus.OK, f"Failed to retrieve circle sensor: {res.errors}"
        assert res['center'] == updated_center, f"Circle center mismatch: expected {updated_center}, got {res['center']}"
        assert res['radius'] == updated_radius, f"Circle radius mismatch: expected {updated_radius}, got {res['radius']}"
        print("Circle area change verified.")

        # Cleanup
        res = self.rest.deleteSensor(sensor_uid_poly)
        assert res.statusCode == HTTPStatus.OK, f"Failed to delete polygon sensor: {res.errors}"
        res = self.rest.deleteSensor(sensor_uid_circle)
        assert res.statusCode == HTTPStatus.OK, f"Failed to delete circle sensor: {res.errors}"
        print("Sensors deleted successfully.")

        return True

def test_sensor_area_main_api(request, record_xml_attribute):
    test = SensorAreaTest(TEST_NAME, request, record_xml_attribute)
    assert test.runTest()
    return
