#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10433-API"

def test_only_upload_glb_main_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  scenes = rest.getScenes({'name': params['scene_name']})['results']
  assert scenes, f"Scene '{params['scene_name']}' not found"
  scene_uid = scenes[0]['uid']

  invalid_files = ["box_invalid.glb", "box.gltf", "box.obj", "good_data.txt"]

  try:
    for f in invalid_files:
      print(f"Trying to upload invalid file: {f}")
      path = os.path.join("tests", "ui", "test_media", f)
      with open(path, "rb") as fp:
        res = rest.updateScene(scene_uid, {"map": fp})
      assert res.statusCode not in (200, 201)
      print(f"Correctly rejected file: {f}")

    print("All invalid files were correctly rejected.")
    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
