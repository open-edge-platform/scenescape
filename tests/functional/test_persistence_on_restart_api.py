#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging

TEST_NAME = "NEX-T10393-RESTART-API"
CAMERA_NAME = "camtest1"

def test_persistence_on_restart_api(params, rest, result_recorder):
  sceneName = params["scene_name"]

  def _cleanup_test_artifacts(scene_uid):
    """Cleanup helper to remove scene + related camera/sensors after the test."""
    # Delete cameras with this name
    cams = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    for c in cams:
      try:
        rest.deleteCamera(c["uid"])
      except Exception:
        pass

    # Delete the scene itself
    try:
      rest.deleteScene(scene_uid)
    except Exception:
      pass

  # After restart, the scene created in the first test should still exist
  scenes = rest.getScenes({"name": sceneName}).get("results", [])
  assert scenes, f"Scene '{sceneName}' not found after restart"
  assert len(scenes) == 1, \
    f"Expected exactly one scene named '{sceneName}', found {len(scenes)}"
  scene = scenes[0]

  assert scene["name"] == sceneName
  assert scene["scale"] in (1000, 100.0), \
    f"Expected scale 1000 or 100.0, got {scene['scale']}"
  assert "map" in scene

  scene_uid = scene["uid"]

  # Validate that the camera created in the first test also survives restart.
  cameras = rest.getCameras({"name": CAMERA_NAME}).get("results", [])
  assert cameras, (
    f"Expected at least one camera named '{CAMERA_NAME}' "
    f"for scene '{sceneName}' after restart"
  )
  cam = cameras[0]
  assert cam.get("name") == CAMERA_NAME, \
    f"Camera name mismatch after restart: expected '{CAMERA_NAME}', got '{cam.get('name')}'"
  if "scene" in cam:
    assert cam["scene"] == scene_uid, \
      f"Camera '{CAMERA_NAME}' is not linked to scene '{sceneName}' after restart"

  print(
    "Scene and camera persist after restart: "
    f"scene='{sceneName}', camera name='{CAMERA_NAME}'"
  )

  # Cleanup so subsequent runs start clean
  _cleanup_test_artifacts(scene_uid)

  result_recorder.success()
