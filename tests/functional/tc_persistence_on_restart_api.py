#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10393-RESTART-API"

class PersistenceOnRestartTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params['scene']
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

  def runTest(self):
    # Validate scene exists after restart (assume DB is persistent)
    scenes = self.rest.getScenes({'name': self.sceneName})['results']
    assert scenes, f"Scene '{self.sceneName}' not found after restart"
    scene = scenes[0]
    assert scene['name'] == self.sceneName
    # Accept both 1000 and 100.0 for scale, as persistent DB may have either
    assert scene['scale'] in (1000, 100.0), f"Expected scale 1000 or 100.0, got {scene['scale']}"
    assert 'map' in scene
    print("Scene persists after restart.")
    # Cleanup
    self.rest.deleteScene(scene['uid'])
    return True

def test_persistence_on_restart_api(request, record_xml_attribute):
  test = PersistenceOnRestartTest(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
