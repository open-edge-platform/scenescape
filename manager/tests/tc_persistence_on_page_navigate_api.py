#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from http import HTTPStatus

TEST_NAME = "NEX-T10393-API"
CAMERA_NAME = "camtest1"
CAMERA_SENSOR_ID = "camtest1"

def test_persistence_on_page_navigate_api(params, rest, result_recorder):
  sceneName = params["scene_name"]

  def _cleanup_test_artifacts():
    """Remove leftover scene/camera/sensors."""
    scenes = rest.getScenes({"name": sceneName}).get("results", [])
    for s in scenes:
      try:
        rest.deleteScene(s["uid"])
      except Exception:
        pass

    cams = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    for c in cams:
      try:
        rest.deleteCamera(c["uid"])
      except Exception:
        pass

    try:
      sensors = rest.getSensors({"sensor_id": CAMERA_SENSOR_ID}).get("results", [])
    except Exception:
      sensors = []
    for s in sensors:
      try:
        rest.deleteSensor(s["uid"])
      except Exception:
        pass

    try:
      sensors_by_name = rest.getSensors({"name": CAMERA_NAME}).get("results", [])
    except Exception:
      sensors_by_name = []
    for s in sensors_by_name:
      try:
        rest.deleteSensor(s["uid"])
      except Exception:
        pass

  # Clean up any existing artifacts so the test is deterministic
  _cleanup_test_artifacts()

  # Create scene
  map_file = os.path.join("sample_data", "HazardZoneScene.png")
  with open(map_file, "rb") as f:
    res = rest.createScene(
      {
        "name": sceneName,
        "scale": 1000,
        "map": f,
      }
    )
  assert res.statusCode == HTTPStatus.CREATED, \
    f"Failed to create scene: {getattr(res, 'errors', res)}"

  # Fetch the scene
  scenes = rest.getScenes({"name": sceneName}).get("results", [])
  assert scenes, f"Scene '{sceneName}' not found after creation"
  assert len(scenes) == 1, \
    f"Expected exactly one scene named '{sceneName}', found {len(scenes)}"
  scene = scenes[0]
  scene_uid = scene["uid"]

  # Add a camera attached to the scene
  cam_payload = {
    "scene": scene_uid,
    "name": CAMERA_NAME,
    "sensor_id": CAMERA_SENSOR_ID,
    "type": "camera",
  }
  res = rest.createCamera(cam_payload)
  assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), \
    f"Failed to add camera: {getattr(res, 'errors', res)}"

  # Validate scene persistence (re-fetch)
  scenes = rest.getScenes({"name": sceneName}).get("results", [])
  assert scenes, f"Scene '{sceneName}' not found after camera creation"
  scene = scenes[0]
  assert scene["name"] == sceneName
  assert scene["scale"] == 1000
  assert "map" in scene

  # Validate camera persistence
  cameras = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
  assert cameras, (
    f"Expected at least one camera named '{CAMERA_NAME}' "
    f"for scene '{sceneName}', but none were found"
  )
  cam = cameras[0]
  assert cam.get("name") == CAMERA_NAME, \
    f"Camera name mismatch: expected '{CAMERA_NAME}', got '{cam.get('name')}'"
  if "scene" in cam:
    assert cam["scene"] == scene_uid, \
      f"Camera '{CAMERA_NAME}' is not linked to scene '{sceneName}'"

  logging.info(
    "Scene and camera persist on page navigation: "
    f"scene='{sceneName}', camera name='{CAMERA_NAME}'"
  )

  result_recorder.success()
