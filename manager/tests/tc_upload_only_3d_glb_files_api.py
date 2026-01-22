#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10433-API"

class OnlyUploadGLBSceneMapTest(FunctionalTest):
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
    invalid_files = [
      "box_invalid.glb",
      "box.gltf",
      "box.obj",
      "good_data.txt"
    ]
    media_path = os.path.join("tests", "ui", "test_media")

    for file_name in invalid_files:
      file_path = os.path.join(media_path, file_name)
      print(f"Trying to upload invalid file: {file_name}")
      with open(file_path, "rb") as f:
        update_data = {"map": f}
        res = self.rest.updateScene(self.scene_uid, update_data)

        # Expecting failure: either 4xx or error message
        assert res.statusCode not in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create scene with .glb: {res.errors}"
        print(f"Correctly rejected file: {file_name}")

    print("All invalid files were correctly rejected.")
    return True

def test_only_upload_glb_main_api(request, record_xml_attribute):
  test = OnlyUploadGLBSceneMapTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
