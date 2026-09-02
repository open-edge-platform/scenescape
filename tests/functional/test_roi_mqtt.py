#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.functional.common_scene_obj import SceneObjectMqtt
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

SCENESCAPE_ENV_MATRIX = {
  "full_stack": "NEX-T10404",
}

TEST_NAME = "NEX-T10404"

def runROIMqttCreate(self):
  self.exitCode = 1
  self.runSceneObjMqttInitialize()
  try:
    self.runSceneObjMqttPrepare()
    self.runROIMqttExecute()
    passed = self.runROIMqttVerifyPassed()
    if passed:
      self.exitCode = 0
  finally:
    self.runSceneObjMqttFinally()
  return

@pytest.mark.basic_acceptance
def test_roi_create(scenescape_env, demo_scene, request, record_xml_attribute):
  test_name = getattr(request.node, '_scenescape_test_name', TEST_NAME)
  test = SceneObjectMqtt(test_name, request, record_xml_attribute)
  runROIMqttCreate(test)
  assert test.exitCode == 0
  return
