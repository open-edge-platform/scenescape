#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
import pytest

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T21876"

@pytest.mark.test_name("NEX-T21876")
def test_only_upload_glb_main_api(rest, scene_uid, result_recorder, demo_scene):
  invalid_files = ["box_invalid.glb", "box.gltf", "box.obj", "good_data.txt"]

  for f in invalid_files:
    log.info(f"Trying to upload invalid file: {f}")
    path = os.path.join("tests", "ui", "test_media", f)
    with open(path, "rb") as fp:
      res = rest.updateScene(scene_uid, {"map": fp})
    assert res.statusCode not in (200, 201)
    log.info(f"Correctly rejected file: {f}")

  log.info("All invalid files were correctly rejected.")

  result_recorder.success()
