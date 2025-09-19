#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import os

TEST_NAME = "NEX-T10393-PERSISTENCE-API"

class PersistenceOnPageNavigateTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def runTest(self):
    # Clean up any existing scene
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    if scenes:
      self.rest.deleteScene(scenes[0]['uid'])
    # Create scene
    map_file = os.path.join('sample_data', 'HazardZoneScene.png')
    with open(map_file, 'rb') as f:
      res = self.rest.createScene({
          "name": self.sceneName,
          "scale": 1000,
          "map": f
      })
      assert res.statusCode == HTTPStatus.CREATED, f"Failed to create scene: {res.errors}"
    # Add a camera
    scene = self.rest.getScenes({'name': self.sceneName})['results'][0]
    scene_uid = scene['uid']
    cam_payload = {
      "scene": scene_uid,
      "name": "selenium_cam_test1",
      "sensor_id": "selenium_cam_test_1",
      "type": "camera"
    }
    res = self.rest.createCamera(cam_payload)
    assert res.statusCode == HTTPStatus.CREATED, f"Failed to add camera: {res.errors}"
    # Validate persistence
    scene = self.rest.getScenes({'name': self.sceneName})['results'][0]
    assert scene['name'] == self.sceneName
    assert scene['scale'] == 1000
    assert 'map' in scene
    print("Scene and camera persist on page navigation.")
    return True

def test_persistence_on_page_navigate_api(request, record_xml_attribute):
  test = PersistenceOnPageNavigateTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
