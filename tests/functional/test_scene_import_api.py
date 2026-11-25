#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import zipfile
import pytest
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
from tests.utils.log import get_logger

log = get_logger(__name__)


SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T13967"
# Imports run synchronously server-side and routinely exceed RESTClient's 10 s default.
IMPORT_TIMEOUT_S = 300

SUCCESS = "0"
EMPTY_ZIP = "1"
INVALID_ZIP = "2"
SCENE_EXISTS = "3"
ORPHANED_CAMERA = "4"
EXPECTS_SCENE_DATA = (SUCCESS, SCENE_EXISTS, ORPHANED_CAMERA)


def describe(res):
  """HTTP status and body of a RESTResult, for logs and assertion messages."""
  body = res.errors if res.errors is not None else dict(res)
  return f"HTTP {res.statusCode}: {body}"


class SceneImportAPITest(FunctionalTest):
  def __init__(self, testName, request, zipFile, expected, repo_root):
    super().__init__(testName, request, None)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"],
                           timeout=IMPORT_TIMEOUT_S)
    auth = self.rest.authenticate(self.params["user"], self.params["password"])
    assert auth, f"REST authentication failed: HTTP {auth.statusCode}: {auth.errors}"

    self.expected = expected
    self.zipFile = os.path.join(repo_root, "tests/ui/test_media", zipFile)
    self.sceneData = None

    if expected == EMPTY_ZIP:
      self.create_empty_zip()
    elif expected in EXPECTS_SCENE_DATA:
      self.sceneData = self.read_json_from_zip()

  def create_empty_zip(self):
    with zipfile.ZipFile(self.zipFile, "w"):
      pass

  def mismatched_fields(self, actual, expected, tol=1e-9):
    """Fields present in both dicts whose values differ beyond float tolerance."""
    mismatches = {}
    for key, val1 in actual.items():
      if key not in expected:
        continue
      val2 = expected[key]
      if isinstance(val1, list) and all(isinstance(x, float) for x in val1):
        equal = val1 == pytest.approx(val2, abs=tol)
      elif isinstance(val1, float):
        equal = val1 == pytest.approx(val2, abs=tol)
      else:
        equal = val1 == val2
      if not equal:
        mismatches[key] = {"actual": val1, "expected": val2}
    return mismatches

  def read_json_from_zip(self):
    with zipfile.ZipFile(self.zipFile, "r") as zip_ref:
      json_files = [f for f in zip_ref.namelist() if f.endswith(".json")]
      assert json_files, f"No JSON file inside {self.zipFile}"
      with zip_ref.open(json_files[0]) as json_file:
        return json.load(json_file)

  def is_error_response(self, response):
    # Failed imports return HTTP 400; RESTClient puts that body in .errors, not the dict.
    return response.errors is not None

  def import_scene(self):
    res = self.rest.importScene(self.zipFile)
    log.info(f"Import {os.path.basename(self.zipFile)} -> {describe(res)}")
    return res

  def get_scene_uid_by_name(self, name):
    res = self.rest.getScenes({"name": name})
    scenes = res.get("results", [])
    assert scenes, f"Scene '{name}' not found ({describe(res)})"
    return scenes[0]["uid"]

  def cleanup_scene(self):
    """Remove the archive's scenes, child scenes, cameras and sensors from the shared stack."""
    if self.sceneData:
      self._cleanup(self.sceneData)

  def _cleanup(self, scene):
    for child in scene.get("children", []):
      self._cleanup(child)
    self._delete_by_name("scene", self.rest.getScenes, self.rest.deleteScene, scene["name"])
    for cam in scene.get("cameras", []):
      self._delete_by_name("camera", self.rest.getCameras, self.rest.deleteCamera, cam["name"])
    for sensor in scene.get("sensors", []):
      self._delete_by_name("sensor", self.rest.getSensors, self.rest.deleteSensor, sensor["name"])

  def _delete_by_name(self, kind, list_fn, delete_fn, name):
    res = list_fn({"name": name})
    if res.errors is not None:
      log.warning(f"Cleanup: listing {kind} '{name}' failed ({describe(res)})")
      return
    for obj in res.get("results", []):
      deleted = delete_fn(obj["uid"])
      if deleted.errors is not None:
        log.warning(f"Cleanup: deleting {kind} '{name}' ({obj['uid']}) failed ({describe(deleted)})")

  def runTest(self):

    if self.expected in EXPECTS_SCENE_DATA:
      self.cleanup_scene()

    res = self.import_scene()

    if self.expected == EMPTY_ZIP:
      assert self.is_error_response(res), f"Expected empty zip to be rejected, got {describe(res)}"
      log.info("Empty zip correctly rejected.")

    elif self.expected == INVALID_ZIP:
      assert self.is_error_response(res), f"Expected invalid zip to be rejected, got {describe(res)}"
      log.info("Invalid zip correctly rejected.")

    elif self.expected == SCENE_EXISTS:
      assert not self.is_error_response(res), f"Initial import failed: {describe(res)}"
      res_dup = self.import_scene()
      assert self.is_error_response(res_dup), \
        f"Expected duplicate scene to be rejected, got {describe(res_dup)}"
      log.info("Duplicate scene correctly rejected.")

    elif self.expected == ORPHANED_CAMERA:
      assert not self.is_error_response(res), f"Import failed: {describe(res)}"
      self.verify_scene_resources(res)

    elif self.expected == SUCCESS:
      assert not self.is_error_response(res), f"Scene import failed: {describe(res)}"
      self.validate_scene(self.sceneData)

  def verify_scene_resources(self, res):
    """Every archive camera and sensor must end up attached to the imported scene."""
    scene_uid = self.get_scene_uid_by_name(self.sceneData["name"])
    actual_cams = sorted(c["name"] for c in self.rest.getCameras({"scene": scene_uid}).get("results", []))
    actual_sensors = sorted(s["name"] for s in self.rest.getSensors({"scene": scene_uid}).get("results", []))
    expected_cams = sorted(c["name"] for c in self.sceneData.get("cameras", []))
    expected_sensors = sorted(s["name"] for s in self.sceneData.get("sensors", []))
    log.info(f"Scene {scene_uid}: cameras={actual_cams} (relinked: {res.get('cameras_relinked')}), "
             f"sensors={actual_sensors}")
    assert actual_cams == expected_cams, \
      f"Cameras in scene {scene_uid}: expected {expected_cams}, got {actual_cams}"
    assert actual_sensors == expected_sensors, \
      f"Sensors in scene {scene_uid}: expected {expected_sensors}, got {actual_sensors}"

  def validate_scene(self, scene):
    scene_uid = self.get_scene_uid_by_name(scene["name"])

    for cam in scene.get("cameras", []):
      res = self.rest.getCamera(cam["uid"])
      assert res.errors is None, f"Camera '{cam['uid']}' not readable: {describe(res)}"
      actual = {k: v for k, v in res.items() if k != "scene"}
      expected = {k: v for k, v in cam.items() if k not in ("scene", "distortion")}
      mismatches = self.mismatched_fields(actual, expected)
      assert not mismatches, f"Camera '{cam['uid']}' in scene '{scene['name']}' mismatch: {mismatches}"

    for sensor in scene.get("sensors", []):
      res = self.rest.getSensors({"name": sensor["name"]})
      results = res.get("results", [])
      assert results, f"Sensor '{sensor['name']}' not found ({describe(res)})"
      actual = {k: v for k, v in results[0].items() if k not in ("uid", "scene")}
      expected = {k: v for k, v in sensor.items() if k not in ("uid", "scene")}
      mismatches = self.mismatched_fields(actual, expected)
      assert not mismatches, f"Sensor '{sensor['name']}' in scene '{scene['name']}' mismatch: {mismatches}"

    for child in scene.get("children", []):
      self.validate_scene(child)

    log.info(f"Scene '{scene['name']}' ({scene_uid}) components validated.")

@pytest.mark.test_name("NEX-T13967")
@pytest.mark.parametrize(
  "zipFile, expected",
  [
    ("Retail-import.zip", SUCCESS),
    ("Empty.zip", EMPTY_ZIP),
    ("Retail-import.zip", SCENE_EXISTS),
    ("Parent.zip", SUCCESS),
    ("Invalid.zip", INVALID_ZIP),
    ("Retail-import.zip", ORPHANED_CAMERA),
    ("Intersection-Demo.zip", SUCCESS),
  ],
)
def test_scene_import_api(scenescape_env, request, zipFile, expected, repo_root, result_recorder):
  test = SceneImportAPITest(TEST_NAME, request, zipFile, expected, repo_root)
  try:
    test.runTest()
    result_recorder.success()
  finally:
    test.cleanup_scene()
