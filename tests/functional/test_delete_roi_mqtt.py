#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional.common_scene_obj import SceneObjectMqtt

TEST_NAME = "NEX-T10430"

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

def test_roi_delete(request, record_xml_attribute):
  test = SceneObjectMqtt(TEST_NAME, request, record_xml_attribute)
  runROIMqttDelete(test)
  assert test.exitCode == 0
  return

def main():
  return test_roi_delete(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
