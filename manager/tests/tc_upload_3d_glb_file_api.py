#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10425-API"

def test_upload_3d_glb_file_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  scenes = rest.getScenes({'name': params['scene_name']})['results']
  assert scenes, f"Scene '{params['scene_name']}' not found"

  file_name = "box.glb"
  file_path = os.path.join("/workspace/tests/ui/test_media", file_name)

  try:
    # Create a scene and upload file
    with open(file_path, "rb") as f:
      scene_data = {
        "name": "DemoGLBScene",
        "map": f
      }
      res = rest.createScene(scene_data)
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create scene with .glb: {res.errors}"


    print(f"GLB file uploaded to scene '{params['scene_name']}' successfully.")
    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
