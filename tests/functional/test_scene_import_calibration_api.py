#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Camera calibration must survive scene export/import onto another machine.

Covers a fresh target, same-name orphaned cameras, cameras owned by another
scene, and preservation of an exported camera pipeline.
"""

import copy
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

TEST_NAME = "scene-import-calibration"
ARCHIVE = "tests/ui/test_media/Retail-import.zip"
TOLERANCE = 1e-6
# Default timeout is 10s
IMPORT_TIMEOUT = 30


class SceneImportCalibration(FunctionalTest):
  def __init__(self, request, repo_root):
    super().__init__(TEST_NAME, request, None)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"],
                           timeout=IMPORT_TIMEOUT)
    assert self.rest.authenticate(self.params["user"], self.params["password"])
    self.zipPath = os.path.join(repo_root, ARCHIVE)
    with zipfile.ZipFile(self.zipPath, "r") as archive:
      json_name = next(name for name in archive.namelist() if name.endswith(".json"))
      with archive.open(json_name) as scene_file:
        self.sceneData = json.load(scene_file)
    self.archiveCams = {cam["name"]: cam for cam in self.sceneData["cameras"]}

  def importArchive(self, zipPath=None):
    result = self.rest.importScene(zipPath or self.zipPath)
    # Resource conflicts can return HTTP 400 with a scene import summary.
    summary_keys = ("scene", "cameras", "tripwires", "regions", "sensors",
                    "calibration_markers")
    if result.errors is not None:
      summary = result.errors
      assert isinstance(summary, dict) and any(key in summary for key in summary_keys), \
        f"Import request failed: {result.errors}"
      result.update(summary)
    assert not result.get("scene"), f"Scene import rejected: {result.get('scene')}"
    scenes = self.rest.getScenes({"name": self.sceneData["name"]}).get("results", [])
    assert len(scenes) == 1, f"Imported scene '{self.sceneData['name']}' not found"
    return result, scenes[0]["uid"]

  def writeArchive(self, path, sceneData):
    """Write a copy of the source archive with its scene JSON replaced."""
    with zipfile.ZipFile(self.zipPath, "r") as source, zipfile.ZipFile(path, "w") as target:
      for member in source.namelist():
        if member.endswith(".json"):
          target.writestr(member, json.dumps(sceneData))
        else:
          target.writestr(member, source.read(member))
    return str(path)

  def getCameraByName(self, name):
    results = self.rest.getCameras({"name": name}).get("results", [])
    assert len(results) == 1, f"Expected exactly one camera named '{name}', got {results}"
    return results[0]

  def cameraErrorNames(self, result):
    names = set()
    for entry in result.get("cameras") or []:
      _, item = entry
      names.add(item.get("name"))
    return names

  def assertCalibrationMatchesArchive(self, camera, expected):
    name = expected["name"]
    assert camera.get("transform_type") == expected["transform_type"], \
      f"{name}: transform_type {camera.get('transform_type')} != {expected['transform_type']}"
    assert camera.get("transforms"), f"{name}: calibration points missing after import"
    assert camera["transforms"] == pytest.approx(expected["transforms"], abs=TOLERANCE), \
      f"{name}: calibration points differ from export"
    for key, value in expected["intrinsics"].items():
      assert camera["intrinsics"].get(key) == pytest.approx(value, abs=TOLERANCE), \
        f"{name}: intrinsics[{key}] differs from export"
    assert camera.get("resolution") == expected["resolution"], \
      f"{name}: resolution differs"

  def removeImportedObjects(self):
    """Delete the archive's scene, cameras and sensors and confirm they are gone."""
    lookups = [(self.rest.getScenes, self.rest.deleteScene, self.sceneData["name"])]
    lookups += [(self.rest.getCameras, self.rest.deleteCamera, name)
                for name in self.archiveCams]
    lookups += [(self.rest.getSensors, self.rest.deleteSensor, sensor["name"])
                for sensor in self.sceneData.get("sensors", [])]
    for getter, deleter, name in lookups:
      for obj in getter({"name": name}).get("results", []):
        deleter(obj["uid"])
    leftovers = [name for getter, _, name in lookups
                 if getter({"name": name}).get("results")]
    assert not leftovers, f"Could not remove imported objects: {leftovers}"
    return


@pytest.fixture(autouse=True)
def imported_objects_removed(scenescape_env, request, repo_root):
  """Remove the archive's scene, cameras and sensors before and after each test."""
  test = SceneImportCalibration(request, repo_root)
  test.removeImportedObjects()
  yield
  test.removeImportedObjects()


@pytest.mark.test_name("NEX-T31112")
def test_import_preserves_calibration_points(scenescape_env, request, repo_root, result_recorder):
  """
  ## Name
  Scene Import Preserves Calibration Points

  ## Objective
  Verify that importing a scene onto a fresh system creates its cameras with
  the exported calibration points, intrinsics and resolution.

  ## Labels
  - Functional
  - API

  ## Steps
  1. Verify no camera with an exported camera name exists
  2. Import the scene archive via the REST API
  3. Assert the import reports no camera errors
  4. Assert each camera is attached to the imported scene
  5. Assert each camera's transform type, calibration points, intrinsics and
     resolution match the exported values
  """
  test = SceneImportCalibration(request, repo_root)
  for name in test.archiveCams:
    assert not test.rest.getCameras({"name": name}).get("results"), \
      f"Precondition: camera '{name}' must not exist"

  result, scene_uid = test.importArchive()
  assert not result.get("cameras"), f"Unexpected camera import errors: {result.get('cameras')}"

  for name, expected in test.archiveCams.items():
    camera = test.getCameraByName(name)
    assert camera.get("scene") == scene_uid, f"{name}: not attached to imported scene"
    test.assertCalibrationMatchesArchive(camera, expected)

  result_recorder.success()


@pytest.mark.test_name("NEX-T31113")
def test_import_relinks_orphaned_camera_with_calibration(
    scenescape_env, request, repo_root, result_recorder):
  """
  ## Name
  Scene Import Re-links Orphaned Cameras With Calibration

  ## Objective
  Verify that importing a scene attaches existing same-name cameras that have
  no scene to the imported scene and applies the exported calibration.

  ## Labels
  - Functional
  - API

  ## Steps
  1. Create an uncalibrated camera without a scene for each exported camera
     name, reusing the exported sensor ID for one and a different ID for others
  2. Import the scene archive via the REST API
  3. Assert the import reports no camera errors
  4. Assert each camera keeps its existing sensor ID
  5. Assert each camera is attached to the imported scene
  6. Assert each camera's calibration matches the exported values
  """
  test = SceneImportCalibration(request, repo_root)
  orphan_sensor_ids = {}
  for index, (name, expected) in enumerate(test.archiveCams.items()):
    sensor_id = expected["uid"] if index == 0 else f"local-cam{index}"
    created = test.rest.createCamera({"name": name, "sensor_id": sensor_id})
    assert not created.errors, f"Failed to create orphaned camera '{name}': {created.errors}"
    assert not created.get("scene"), f"Precondition: '{name}' must be orphaned"
    assert not created.get("transforms"), f"Precondition: '{name}' must be uncalibrated"
    orphan_sensor_ids[name] = sensor_id

  result, scene_uid = test.importArchive()
  assert not result.get("cameras"), \
    f"Orphaned cameras were not re-linked by import: {result.get('cameras')}"

  for name, expected in test.archiveCams.items():
    camera = test.getCameraByName(name)
    assert camera.get("uid") == orphan_sensor_ids[name], \
      f"{name}: existing sensor_id was replaced"
    assert camera.get("scene") == scene_uid, f"{name}: not attached to imported scene"
    test.assertCalibrationMatchesArchive(camera, expected)

  result_recorder.success()


@pytest.mark.test_name("NEX-T31114")
def test_import_does_not_hijack_camera_in_other_scene(
    scenescape_env, demo_scene, request, repo_root, result_recorder):
  """
  ## Name
  Scene Import Does Not Take Over Camera From Another Scene

  ## Objective
  Verify that importing a scene reports an error for a same-name camera that
  belongs to another scene, leaves that camera unchanged, and still imports
  the remaining cameras with their calibration.

  ## Labels
  - Functional
  - API

  ## Steps
  1. Create a placeholder camera with the first exported camera name in the
     demo scene
  2. Import the scene archive via the REST API
  3. Assert the import reports an error for the placeholder camera
  4. Assert the placeholder camera keeps its sensor ID, scene, transform type
     and calibration
  5. Assert the remaining cameras are attached to the imported scene with the
     exported calibration
  """
  test = SceneImportCalibration(request, repo_root)
  names = list(test.archiveCams)
  owned_name = names[0]
  placeholder = {
    "name": owned_name,
    "sensor_id": "cam-placeholder",
    "scene": demo_scene,
    "transform_type": "quaternion",
    "translation": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0, 1.0],
    "scale": [1.0, 1.0, 1.0],
    "intrinsics": {"fx": 1.0, "fy": 1.0, "cx": 1.0, "cy": 1.0},
  }
  created = test.rest.createCamera(placeholder)
  assert not created.errors, f"Failed to create placeholder camera: {created.errors}"
  before = test.getCameraByName(owned_name)

  result, scene_uid = test.importArchive()
  assert owned_name in test.cameraErrorNames(result), \
    f"Expected an import error for '{owned_name}', got {result.get('cameras')}"

  after = test.getCameraByName(owned_name)
  assert after.get("uid") == before.get("uid"), "Existing camera was replaced"
  assert after.get("scene") == demo_scene, "Existing camera was moved to the imported scene"
  assert after.get("transform_type") == before.get("transform_type"), \
    "Existing camera transform_type was overwritten"
  assert after.get("transforms") == pytest.approx(before.get("transforms"), abs=TOLERANCE), \
    "Existing camera calibration was overwritten"

  for name in names[1:]:
    camera = test.getCameraByName(name)
    assert camera.get("scene") == scene_uid, f"{name}: not attached to imported scene"
    test.assertCalibrationMatchesArchive(camera, test.archiveCams[name])

  result_recorder.success()


@pytest.mark.test_name("NEX-T31115")
def test_import_preserves_camera_pipeline(
    scenescape_env, request, repo_root, tmp_path, result_recorder):
  """
  ## Name
  Scene Import Preserves Camera Pipeline

  ## Objective
  Verify that cameras exported with use_camera_pipeline enabled keep their
  pipeline and calibration after import, both when an orphaned camera is
  re-linked and when a camera is created.

  ## Labels
  - Functional
  - API

  ## Steps
  1. Build a copy of the archive with use_camera_pipeline enabled and a
     camera_pipeline set on every camera
  2. Create an orphaned camera with the first exported camera name
  3. Verify no camera with the remaining exported names exists
  4. Import the modified archive via the REST API
  5. Assert the import reports no camera errors and lists the orphaned camera
     as re-linked
  6. Assert each camera is attached to the imported scene with
     use_camera_pipeline, camera_pipeline and calibration preserved
  """
  test = SceneImportCalibration(request, repo_root)
  pipeline = "videotestsrc ! fakesink"
  scene_data = copy.deepcopy(test.sceneData)
  for camera_data in scene_data["cameras"]:
    camera_data["use_camera_pipeline"] = True
    camera_data["camera_pipeline"] = pipeline
  zip_path = test.writeArchive(tmp_path / os.path.basename(ARCHIVE), scene_data)

  names = list(test.archiveCams)
  orphan_name = names[0]
  created = test.rest.createCamera({"name": orphan_name, "sensor_id": "local-cam0"})
  assert not created.errors, f"Failed to create orphaned camera: {created.errors}"
  for name in names[1:]:
    assert not test.rest.getCameras({"name": name}).get("results"), \
      f"Precondition: camera '{name}' must not exist"

  result, scene_uid = test.importArchive(zip_path)
  assert not result.get("cameras"), f"Unexpected camera import errors: {result.get('cameras')}"
  assert orphan_name in {camera.get("name") for camera in result.get("cameras_relinked") or []}, \
    f"'{orphan_name}' was not re-linked"

  for name, expected in test.archiveCams.items():
    camera = test.getCameraByName(name)
    assert camera.get("scene") == scene_uid, f"{name}: not attached to imported scene"
    assert camera.get("use_camera_pipeline") is True, f"{name}: use_camera_pipeline lost"
    assert camera.get("camera_pipeline") == pipeline, f"{name}: camera_pipeline lost"
    test.assertCalibrationMatchesArchive(camera, expected)

  result_recorder.success()
