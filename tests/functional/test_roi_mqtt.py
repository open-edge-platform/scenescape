#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional.common_scene_obj import SceneObjectMqtt

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

def test_roi_create(request, record_xml_attribute):
  test = SceneObjectMqtt(TEST_NAME, request, record_xml_attribute)
  runROIMqttCreate(test)
  assert test.exitCode == 0
  return

def main():
  return test_roi_create(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
