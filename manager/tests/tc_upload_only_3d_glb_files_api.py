#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import logging

TEST_NAME = "NEX-T10433-API"

def test_only_upload_glb_main_api(rest, scene_uid, result_recorder):
  invalid_files = ["box_invalid.glb", "box.gltf", "box.obj", "good_data.txt"]

  for f in invalid_files:
    logging.info(f"Trying to upload invalid file: {f}")
    path = os.path.join("tests", "ui", "test_media", f)
    with open(path, "rb") as fp:
      res = rest.updateScene(scene_uid, {"map": fp})
    assert res.statusCode not in (200, 201)
    logging.info(f"Correctly rejected file: {f}")

  logging.info("All invalid files were correctly rejected.")

  result_recorder.success()
