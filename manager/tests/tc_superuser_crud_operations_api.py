#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10418-API"

class CRUDPermissionsTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.scene_uid = None
    self.camera_uid = None
    self.test_user = "testuser"
    self.test_pwd = "#dummy_pwd123"

  def setUp(self):
    self.rest_admin = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest_admin.authenticate(self.params["user"], self.params["password"]), "Admin authentication failed"

    user_data = {
      "username": self.test_user,
      "password": self.test_pwd,
      "is_admin": False,
    }
    res = self.rest_admin.createUser(user_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create test user: {res.errors}"

    self.rest_user = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest_user.authenticate(self.test_user, self.test_pwd), "Test user authentication failed"

    existing = self.rest_admin.getScenes({"name": "TestScene"})["results"]
    if existing:
      self.rest_admin.deleteScene(existing[0]["uid"])

    map_image = "/workspace/sample_data/HazardZoneSceneLarge.png"
    assert os.path.exists(map_image), f"Map image not found: {map_image}"
    with open(map_image, "rb") as f:
      map_data = f.read()

    scene_data = {
      "name": "TestScene",
      "scale": 100,
      "map": (map_image, map_data)
    }
    res = self.rest_admin.createScene(scene_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Admin failed to create scene: {res.errors}"
    self.scene_uid = res["uid"]

    camera_data = {
      'name': "TestCamera1",
      'sensor_id': "TestCamera1",
      'scene': self.scene_uid,
      'intrinsics': {
        'fx': 800.0,
        'fy': 800.0,
        'cx': 320.0,
        'cy': 240.0
      }
    }
    res = self.rest_admin.createCamera(camera_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Admin failed to create camera: {res.errors}"
    self.camera_uid = res["uid"]

  def tearDown(self):
    if self.camera_uid:
      self.rest_admin.deleteCamera(self.camera_uid)
    if self.scene_uid:
      self.rest_admin.deleteScene(self.scene_uid)
    self.rest_admin.deleteUser(self.test_user)

  def runTest(self):
    self.setUp()
    try:
      sensor_data = {
        "name": "test_sensor1",
        "sensor_id": "test_sensor_1",
        "area": "scene",
        "scene": self.scene_uid
      }
      res = self.rest_admin.createSensor(sensor_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Expected OK/CREATED, got {res.statusCode} for sensor creation"
      sensor_uid = res["uid"]

      region_data = {
        "name": "test_region1",
        "scene": self.scene_uid,
        "points": [[0, 0], [1, 0], [1, 1], [0, 1]]
      }
      res = self.rest_admin.createRegion(region_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Expected OK/CREATED, got {res.statusCode} for region creation"
      region_uid = res["uid"]

      tripwire_data = {
        "name": "test_tripwire1",
        "scene": self.scene_uid,
        "points": [[0, 0], [1, 1]]
      }
      res = self.rest_admin.createTripwire(tripwire_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Expected OK/CREATED, got {res.statusCode} for tripwire creation"
      tripwire_uid = res["uid"]

      update_data = {
        "intrinsics": {
          "fx": 850.0, "fy": 860.0, "cx": 330.0, "cy": 340.0
        },
        "distortion": {
          "k1": 0.1, "k2": 0.01, "p1": 0.001, "p2": 0.001, "k3": 0.005
        }
      }
      res = self.rest_admin.updateCamera(self.camera_uid, update_data)
      assert res.statusCode == HTTPStatus.OK, f"Expected OK, got {res.statusCode} for camera update"

      res = self.rest_user.updateCamera(self.camera_uid, update_data)
      assert res.statusCode == HTTPStatus.FORBIDDEN, f"Expected FORBIDDEN, got {res.statusCode} for unprivileged camera update"

      for label, method, data in [
        ("createSensor", self.rest_user.createSensor, sensor_data),
        ("createRegion", self.rest_user.createRegion, region_data),
        ("createTripwire", self.rest_user.createTripwire, tripwire_data),
      ]:
        res = method(data)
        assert res.statusCode == HTTPStatus.FORBIDDEN, f"Expected FORBIDDEN, got {res.statusCode} for {label}"

      print("Admin successfully performed all CRUD operations.")
      print("Unprivileged user was correctly denied access to all CRUD operations.")

      self.rest_admin.deleteTripwire(tripwire_uid)
      self.rest_admin.deleteRegion(region_uid)
      self.rest_admin.deleteSensor(sensor_uid)

      return True
    finally:
      self.tearDown()

def test_crud_operations_api(request, record_xml_attribute):
  test = CRUDPermissionsTest(TEST_NAME, request, record_xml_attribute)
