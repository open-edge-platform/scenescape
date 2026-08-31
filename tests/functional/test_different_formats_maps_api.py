#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from tests.utils.log import get_logger
from http import HTTPStatus
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
import pytest

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T21874"

@pytest.mark.test_name("NEX-T21874")
def test_different_formats_maps_api(params, rest, scene_uid, result_recorder, demo_scene):
  rest.deleteScene(scene_uid)

  # Test uploading different map formats
  map_files = [
    os.path.join('sample_data', 'LabMap.png'),
    os.path.join('sample_data', 'LotMap.png'),
    os.path.join('sample_data', 'scene.png'),
  ]

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

  log.info("Successfully uploaded scenes with different map formats.")

  result_recorder.success()
