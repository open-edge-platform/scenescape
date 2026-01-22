#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from tests.functional import FunctionalTest
from http import HTTPStatus
from scene_common.rest_client import RESTClient
import os

TEST_NAME = "NEX-T10393-API"
CAMERA_NAME = "camtest1"
CAMERA_SENSOR_ID = "camtest1"

class PersistenceOnPageNavigateTestAPI(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.sceneName = self.params["scene"]
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

  def _cleanup_test_artifacts(self):
    """Remove leftover scene/camera/sensors."""
    scenes = self.rest.getScenes({"name": self.sceneName}).get("results", [])
    for s in scenes:
      try:
        self.rest.deleteScene(s["uid"])
      except Exception:
        pass

    cams = self.rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    for c in cams:
      try:
        self.rest.deleteCamera(c["uid"])
      except Exception:
        pass

    try:
      sensors = self.rest.getSensors({"sensor_id": CAMERA_SENSOR_ID}).get("results", [])
    except Exception:
      sensors = []
    for s in sensors:
      try:
        self.rest.deleteSensor(s["uid"])
      except Exception:
        pass

    try:
      sensors_by_name = self.rest.getSensors({"name": CAMERA_NAME}).get("results", [])
    except Exception:
      sensors_by_name = []
    for s in sensors_by_name:
      try:
        self.rest.deleteSensor(s["uid"])
      except Exception:
        pass

  def runTest(self):
    # Clean up any existing artifacts so the test is deterministic
    self._cleanup_test_artifacts()

    # Create scene
    map_file = os.path.join("sample_data", "HazardZoneScene.png")
    with open(map_file, "rb") as f:
      res = self.rest.createScene(
        {
          "name": self.sceneName,
          "scale": 1000,
          "map": f,
        }
      )
    assert res.statusCode == HTTPStatus.CREATED, \
      f"Failed to create scene: {getattr(res, 'errors', res)}"

    # Fetch the scene
    scenes = self.rest.getScenes({"name": self.sceneName}).get("results", [])
    assert scenes, f"Scene '{self.sceneName}' not found after creation"
    assert len(scenes) == 1, \
      f"Expected exactly one scene named '{self.sceneName}', found {len(scenes)}"
    scene = scenes[0]
    scene_uid = scene["uid"]

    # Add a camera attached to the scene
    cam_payload = {
      "scene": scene_uid,
      "name": CAMERA_NAME,
      "sensor_id": CAMERA_SENSOR_ID,
      "type": "camera",
    }
    res = self.rest.createCamera(cam_payload)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), \
      f"Failed to add camera: {getattr(res, 'errors', res)}"

    # Validate scene persistence (re-fetch)
    scenes = self.rest.getScenes({"name": self.sceneName}).get("results", [])
    assert scenes, f"Scene '{self.sceneName}' not found after camera creation"
    scene = scenes[0]
    assert scene["name"] == self.sceneName
    assert scene["scale"] == 1000
    assert "map" in scene

    # Validate camera persistence
    cameras = self.rest.getCameras({"name": CAMERA_NAME}).get("results", [])
    assert cameras, (
      f"Expected at least one camera named '{CAMERA_NAME}' "
      f"for scene '{self.sceneName}', but none were found"
    )
    cam = cameras[0]
    assert cam.get("name") == CAMERA_NAME, \
      f"Camera name mismatch: expected '{CAMERA_NAME}', got '{cam.get('name')}'"
    if "scene" in cam:
      assert cam["scene"] == scene_uid, \
        f"Camera '{CAMERA_NAME}' is not linked to scene '{self.sceneName}'"

    print(
      "Scene and camera persist on page navigation: "
      f"scene='{self.sceneName}', camera name='{CAMERA_NAME}'"
    )
    return True

def test_persistence_on_page_navigate_api(request, record_xml_attribute):
  test = PersistenceOnPageNavigateTestAPI(TEST_NAME, request, record_xml_attribute)
  assert test.runTest()
