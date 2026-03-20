#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from tests.functional.common_scene_obj import SceneObjectMqtt

def runROIMqttCreate(self):
  self.exitCode = 1
    # while (true):
    #   pass
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

@pytest.mark.test_ids(default="NEX-T10404", analytics="NEX-T12345")
def test_roi_create(request, record_xml_attribute, test_id):
  test = SceneObjectMqtt(test_id, request, record_xml_attribute)
  runROIMqttCreate(test)
  assert test.exitCode == 0

def main():
  return test_roi_create(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
