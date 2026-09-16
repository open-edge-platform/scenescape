#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional.common_scene_obj import SceneObjectMqtt
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
import pytest

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

def runROIMqttDelete(self):
  self.exitCode = 1
  self.runSceneObjMqttInitialize()
  try:
    self.runSceneObjMqttPrepare()
    self.runROIMqttExecute()
    self.runROIMqttDelete()
    passed_after_delete = self.runROIMqttVerifyNoEventsAfterDelete()
    if passed_after_delete:
      self.exitCode = 0
  finally:
    self.runSceneObjMqttFinally()
  return

@pytest.mark.test_name("NEX-T29295")
def test_roi_delete(scenescape_env, request, record_xml_attribute):
  """! An ROI's region-entry/exit MQTT events stop after the ROI is deleted.

  @param    scenescape_env        Pytest fixture providing the running stack.
  @param    request                Pytest request fixture.
  @param    record_xml_attribute  Pytest fixture recording the test name.
  """
  test = SceneObjectMqtt("NEX-T29295", request, record_xml_attribute)
  runROIMqttDelete(test)
  assert test.exitCode == 0
  return

def main():
  return test_roi_delete(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
