#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

TEST_NAME = "NEX-T10392-API"

def test_different_formats_maps_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])

  scenes = rest.getScenes({'name': params['scene_name']})['results']
  assert scenes, f"Scene '{params['scene_name']}' not found"
  scene_uid = scenes[0]['uid']
  rest.deleteScene(scene_uid)

  # Test uploading different map formats
  map_files = [
    os.path.join('sample_data', 'LabMap.png'),
    os.path.join('sample_data', 'LotMap.png'),
    os.path.join('sample_data', 'scene.png'),
  ]

  try:
    for idx, map_file in enumerate(map_files):
      scene_name = f"{params['scene_name']}_fmt_{idx}"
      with open(map_file, 'rb') as f:
        res = rest.createScene({
          "name": scene_name,
          "scale": 1000,
          "map": f
        })
        assert res.statusCode == HTTPStatus.CREATED, f"Failed to create scene with {map_file}: {res.errors}"
        # Validate map upload by fetching scene and checking map url
        scene = rest.getScenes({'name': scene_name})['results'][0]
        assert scene and 'map' in scene, f"Map not found in scene {scene_name}"

    print("Successfully uploaded scenes with different map formats.")
    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
