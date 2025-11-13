#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10395-API"

class SceneDetailsAPITest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

    self.scene_name = "Demo"

  def runTest(self):
    # Fetch scene by name
    res = self.rest.getScenes({"name": self.scene_name})
    assert res.statusCode == HTTPStatus.OK, f"Failed to fetch scenes: {res.errors}"
    scenes = res["results"]
    assert scenes, f"Scene '{self.scene_name}' not found"
    scene = scenes[0]
    scene_uid = scene["uid"]
    print(f"Scene '{self.scene_name}' found with UID: {scene_uid}")

    # Fetch scene details
    res = self.rest.getScene(scene_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to fetch scene details: {res.errors}"
    assert res["name"] == self.scene_name, f"Scene name mismatch: expected '{self.scene_name}', got '{res['name']}'"
    print("Scene name verified.")

    # Check for map image
    assert "map" in res and res["map"], "Map image not found in scene details"
    print("Map image verified.")

    # Check for cameras
    res_cameras = self.rest.getCameras({"scene": scene_uid})
    assert res_cameras.statusCode == HTTPStatus.OK, f"Failed to fetch cameras: {res_cameras.errors}"
    cameras = res_cameras["results"]
    assert cameras, "No cameras found in scene"
    print(f"{len(cameras)} camera(s) found in scene.")

    return True

def test_scene_details_api(request, record_xml_attribute):
  test = SceneDetailsAPITest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
