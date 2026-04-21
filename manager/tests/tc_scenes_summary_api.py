#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10394-API"

class SceneSummaryAPITest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

  def runTest(self):
    scene_name_0 = "Demo"
    scene_name_1 = "Scene-1"
    scale = 1000
    map_image_path = "SampleJpegMap.jpeg"

    # Create second scene
    scene_data = {
      "name": scene_name_1,
      "scale": scale,
      "map_image": map_image_path
    }
    res = self.rest.createScene(scene_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Scene creation failed: {res.errors}"
    scene_uid_1 = res["uid"]
    print(f"Scene '{scene_name_1}' created successfully.")

    # Fetch all scenes
    res = self.rest.getScenes({})
    assert res.statusCode == HTTPStatus.OK, f"Failed to fetch scenes: {res.errors}"
    scene_names = [scene["name"] for scene in res["results"]]
    print(f"Available scenes: {scene_names}")

    # Check that both scenes are present
    assert scene_name_0 in scene_names, f"Scene '{scene_name_0}' not found in summary."
    assert scene_name_1 in scene_names, f"Scene '{scene_name_1}' not found in summary."
    assert len(scene_names) >= 2, "Expected at least two scenes in summary."

    # Cleanup
    res = self.rest.deleteScene(scene_uid_1)
    assert res.statusCode == HTTPStatus.OK, f"Failed to delete scene '{scene_name_1}': {res.errors}"
    print(f"Scene '{scene_name_1}' deleted successfully.")

    return True

def test_scene_summary_api(request, record_xml_attribute):
  test = SceneSummaryAPITest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
