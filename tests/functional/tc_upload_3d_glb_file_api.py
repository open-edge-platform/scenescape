#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import os

TEST_NAME = "NEX-T10425-API"

class UploadGLBSceneMapTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    # Get scene UID by name
    self.scene_name = self.params['scene']
    scenes = self.rest.getScenes({'name': self.scene_name})['results']
    assert scenes and len(scenes) > 0, f"Scene '{self.scene_name}' not found"
    self.scene_uid = scenes[0]['uid']

  def runTest(self):
    file_name = "box.glb"
    file_path = os.path.join("/workspace/tests/ui/test_media", file_name)

    # Create a scene and upload file
    with open(file_path, "rb") as f:
      scene_data = {
        "name": "DemoGLBScene",
        "map": f
      }
      res = self.rest.createScene(scene_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create scene with .glb: {res.errors}"


    print(f"GLB file uploaded to scene '{self.scene_name}' successfully.")
    return True


def test_upload_glb_scene_map_api(request, record_xml_attribute):
  test = UploadGLBSceneMapTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
