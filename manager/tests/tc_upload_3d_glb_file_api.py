#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import logging
from http import HTTPStatus

TEST_NAME = "NEX-T10425-API"

def test_upload_3d_glb_file_api(rest, result_recorder):
  file_name = "box.glb"
  file_path = os.path.join("/workspace/tests/ui/test_media", file_name)

  # Create a scene and upload file
  with open(file_path, "rb") as f:
    scene_data = {
      "name": "DemoGLBScene",
      "map": f
    }
    res = rest.createScene(scene_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), f"Failed to create scene with .glb: {res.errors}"


  logging.info(f"GLB file uploaded to scene '{scene_data['name']}' successfully.")

  result_recorder.success()
