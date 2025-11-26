#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10393-RESTART-API"
CAMERA_NAME = "camtest1"

class PersistenceOnRestartTestAPI(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params["scene"]
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

  def _cleanup_test_artifacts(self, scene_uid):
    """Cleanup helper to remove scene + related camera/sensors after the test."""
    # Delete cameras with this name
    cams = self.rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    for c in cams:
      try:
        self.rest.deleteCamera(c["uid"])
      except Exception:
        pass

    # Delete the scene itself
    try:
      self.rest.deleteScene(scene_uid)
    except Exception:
      pass

  def runTest(self):
    # After restart, the scene created in the first test should still exist
    scenes = self.rest.getScenes({"name": self.sceneName}).get("results", [])
    assert scenes, f"Scene '{self.sceneName}' not found after restart"
    assert len(scenes) == 1, \
      f"Expected exactly one scene named '{self.sceneName}', found {len(scenes)}"
    scene = scenes[0]

    assert scene["name"] == self.sceneName
    assert scene["scale"] in (1000, 100.0), \
      f"Expected scale 1000 or 100.0, got {scene['scale']}"
    assert "map" in scene

    scene_uid = scene["uid"]

    # Validate that the camera created in the first test also survives restart.
    cameras = self.rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    assert cameras, (
      f"Expected at least one camera named '{CAMERA_NAME}' "
      f"for scene '{self.sceneName}' after restart"
    )
    cam = cameras[0]
    assert cam.get("name") == CAMERA_NAME, \
      f"Camera name mismatch after restart: expected '{CAMERA_NAME}', got '{cam.get('name')}'"
    if "scene" in cam:
      assert cam["scene"] == scene_uid, \
        f"Camera '{CAMERA_NAME}' is not linked to scene '{self.sceneName}' after restart"

    print(
      "Scene and camera persist after restart: "
      f"scene='{self.sceneName}', camera name='{CAMERA_NAME}'"
    )

    # Cleanup so subsequent runs start clean
    self._cleanup_test_artifacts(scene_uid)
    return True

def test_persistence_on_restart_api(request, record_xml_attribute):
  test = PersistenceOnRestartTestAPI(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
