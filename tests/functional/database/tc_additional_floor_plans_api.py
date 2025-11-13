#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import os

TEST_NAME = "NEX-T10405-API"

class AdditionalFloorPlansTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def runTest(self):
    # Get scene UID
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    assert scenes and len(scenes) > 0, f"Scene '{self.sceneName}' not found"
    scene_uid = scenes[0]['uid']

    # Upload additional floor plans
    floor_plan_files = [
      os.path.join('sample_data', 'HazardZoneScene.png'),
      # Add more files as needed
    ]
    for file_path in floor_plan_files:
      with open(file_path, 'rb') as f:
        # Use updateScene with 'map' field for file upload
        res = self.rest.updateScene(scene_uid, {"map": f})
        assert res.statusCode == HTTPStatus.OK, f"Failed to upload {file_path}: {res.errors}"

    print("Successfully uploaded additional floor plans.")
    return True

def test_additional_floor_plans_api(request, record_xml_attribute):
  test = AdditionalFloorPlansTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
  return
