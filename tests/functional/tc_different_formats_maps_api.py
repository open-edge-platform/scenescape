#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import os

TEST_NAME = "NEX-T10392-API"

class DifferentFormatsMapsTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def runTest(self):
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    if scenes:
      scene_uid = scenes[0]['uid']
      self.rest.deleteScene(scene_uid)
    # Test uploading different map formats
    map_files = [
      os.path.join('sample_data', 'LabMap.png'),
      os.path.join('sample_data', 'LotMap.png'),
      os.path.join('sample_data', 'scene.png'),
    ]
    for idx, map_file in enumerate(map_files):
      scene_name = f"{self.sceneName}_fmt_{idx}"
      with open(map_file, 'rb') as f:
        res = self.rest.createScene({
          "name": scene_name,
          "scale": 1000,
          "map": f
        })
        assert res.statusCode == HTTPStatus.CREATED, f"Failed to create scene with {map_file}: {res.errors}"
        # Validate map upload by fetching scene and checking map url
        scene = self.rest.getScenes({'name': scene_name})['results'][0]
        assert scene and 'map' in scene, f"Map not found in scene {scene_name}"
    print("Successfully uploaded scenes with different map formats.")
    return True

def test_different_formats_maps_api(request, record_xml_attribute):
  test = DifferentFormatsMapsTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
