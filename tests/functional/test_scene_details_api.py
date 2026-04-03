#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK_WITH_VIDEO_AND_RETAIL
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

logger = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  id="scene_details_api", profile=FULL_STACK_WITH_VIDEO_AND_RETAIL,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T10395-API"

def test_scene_details_api(params, record_xml_attribute):
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"])

  scene_name = "Demo"

  try:
    # Fetch scene by name
    res = rest.getScenes({"name": scene_name})
    assert res.statusCode == HTTPStatus.OK, f"Failed to fetch scenes: {res.errors}"
    scenes = res["results"]
    assert scenes, f"Scene '{scene_name}' not found"
    scene = scenes[0]
    scene_uid = scene["uid"]
    logger.info("Scene '%s' found with UID: %s", scene_name, scene_uid)

    # Fetch scene details
    res = rest.getScene(scene_uid)
    assert res.statusCode == HTTPStatus.OK, f"Failed to fetch scene details: {res.errors}"
    assert res["name"] == scene_name, f"Scene name mismatch: expected '{scene_name}', got '{res['name']}'"
    logger.info("Scene name verified.")

    # Check for map image
    assert "map" in res and res["map"], "Map image not found in scene details"
    logger.info("Map image verified.")

    # Check for cameras
    res_cameras = rest.getCameras({"scene": scene_uid})
    assert res_cameras.statusCode == HTTPStatus.OK, f"Failed to fetch cameras: {res_cameras.errors}"
    cameras = res_cameras["results"]
    assert cameras, "No cameras found in scene"
    logger.info("%d camera(s) found in scene.", len(cameras))

    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
