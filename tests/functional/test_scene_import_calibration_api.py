#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Camera calibration must survive scene export/import onto another machine.

Covers the possible states of the target machine before the import:
a fresh install, a same-name camera left without a scene (orphaned), and a
same-name camera already attached to another scene. Also checks that a
camera exported with use_camera_pipeline enabled keeps its pipeline.
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


class SceneImportCalibration(FunctionalTest):
  def __init__(self, request, repo_root):
    super().__init__(TEST_NAME, request, None)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])
    self.zipPath = os.path.join(repo_root, ARCHIVE)
    with zipfile.ZipFile(self.zipPath, "r") as zf:
      jsonName = next(n for n in zf.namelist() if n.endswith(".json"))
      with zf.open(jsonName) as f:
        self.sceneData = json.load(f)
    self.archiveCams = {cam["name"]: cam for cam in self.sceneData["cameras"]}
    return

  def importArchive(self, zipPath=None):
    res = self.rest.importScene(zipPath or self.zipPath)
    assert not res.errors, f"Import request failed: {res.errors}"
    assert not res.get("scene"), f"Scene import rejected: {res.get('scene')}"
    scenes = self.rest.getScenes({"name": self.sceneData["name"]}).get("results", [])
    assert len(scenes) == 1, f"Imported scene '{self.sceneData['name']}' not found"
    return res, scenes[0]["uid"]

  def writeArchive(self, path, sceneData):
    """Writes a copy of the source archive with its scene JSON replaced."""
    with zipfile.ZipFile(self.zipPath, "r") as src, zipfile.ZipFile(path, "w") as dst:
      for member in src.namelist():
        if member.endswith(".json"):
          dst.writestr(member, json.dumps(sceneData))
        else:
          dst.writestr(member, src.read(member))
    return str(path)

  def getCameraByName(self, name):
    results = self.rest.getCameras({"name": name}).get("results", [])
    assert len(results) == 1, f"Expected exactly one camera named '{name}', got {results}"
    return results[0]

  def cameraErrorNames(self, res):
    names = set()
    for entry in res.get("cameras") or []:
      _, item = entry
      names.add(item.get("name"))
    return names

  def assertCalibrationMatchesArchive(self, cam, expected):
    name = expected["name"]
    assert cam.get("transform_type") == expected["transform_type"], \
      f"{name}: transform_type {cam.get('transform_type')} != {expected['transform_type']}"
    assert cam.get("transforms"), f"{name}: calibration points missing after import"
    assert cam["transforms"] == pytest.approx(expected["transforms"], abs=TOLERANCE), \
      f"{name}: calibration points differ from export"
    for key, val in expected["intrinsics"].items():
      assert cam["intrinsics"].get(key) == pytest.approx(val, abs=TOLERANCE), \
        f"{name}: intrinsics[{key}] differs from export"
    assert cam.get("resolution") == expected["resolution"], f"{name}: resolution differs"
    return


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

  res, sceneUID = test.importArchive()
  assert not res.get("cameras"), f"Unexpected camera import errors: {res.get('cameras')}"

  for name, expected in test.archiveCams.items():
    cam = test.getCameraByName(name)
    assert cam.get("scene") == sceneUID, f"{name}: not attached to imported scene"
    test.assertCalibrationMatchesArchive(cam, expected)

  result_recorder.success()
  return


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
  # One orphan reuses the exported sensor_id, the other has a different one,
  # as when the target machine was set up independently.
  orphanSensorIds = {}
  for idx, (name, expected) in enumerate(test.archiveCams.items()):
    sensorId = expected["uid"] if idx == 0 else f"local-cam{idx}"
    created = test.rest.createCamera({"name": name, "sensor_id": sensorId})
    assert not created.errors, f"Failed to create orphaned camera '{name}': {created.errors}"
    assert not created.get("scene"), f"Precondition: '{name}' must be orphaned"
    assert not created.get("transforms"), f"Precondition: '{name}' must be uncalibrated"
    orphanSensorIds[name] = sensorId

  res, sceneUID = test.importArchive()
  assert not res.get("cameras"), \
    f"Orphaned cameras were not re-linked by import: {res.get('cameras')}"

  for name, expected in test.archiveCams.items():
    cam = test.getCameraByName(name)
    assert cam.get("uid") == orphanSensorIds[name], f"{name}: existing sensor_id was replaced"
    assert cam.get("scene") == sceneUID, f"{name}: not attached to imported scene"
    test.assertCalibrationMatchesArchive(cam, expected)

  result_recorder.success()
  return


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
  ownedName = names[0]
  # Mirrors the placeholder created by the scenescape-setup flow.
  placeholder = {
    "name": ownedName,
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
  before = test.getCameraByName(ownedName)

  res, sceneUID = test.importArchive()
  assert ownedName in test.cameraErrorNames(res), \
    f"Expected an import error for '{ownedName}', got {res.get('cameras')}"

  after = test.getCameraByName(ownedName)
  assert after.get("uid") == before.get("uid"), "Existing camera was replaced"
  assert after.get("scene") == demo_scene, "Existing camera was moved to the imported scene"
  assert after.get("transform_type") == before.get("transform_type"), \
    "Existing camera transform_type was overwritten"
  assert after.get("transforms") == pytest.approx(before.get("transforms"), abs=TOLERANCE), \
    "Existing camera calibration was overwritten"

  for name in names[1:]:
    cam = test.getCameraByName(name)
    assert cam.get("scene") == sceneUID, f"{name}: not attached to imported scene"
    test.assertCalibrationMatchesArchive(cam, test.archiveCams[name])

  result_recorder.success()
  return


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
  sceneData = copy.deepcopy(test.sceneData)
  for cam in sceneData["cameras"]:
    cam["use_camera_pipeline"] = True
    cam["camera_pipeline"] = pipeline
  zipPath = test.writeArchive(tmp_path / os.path.basename(ARCHIVE), sceneData)

  names = list(test.archiveCams)
  orphanName = names[0]
  created = test.rest.createCamera({"name": orphanName, "sensor_id": "local-cam0"})
  assert not created.errors, f"Failed to create orphaned camera: {created.errors}"
  for name in names[1:]:
    assert not test.rest.getCameras({"name": name}).get("results"), \
      f"Precondition: camera '{name}' must not exist"

  res, sceneUID = test.importArchive(zipPath)
  assert not res.get("cameras"), f"Unexpected camera import errors: {res.get('cameras')}"
  assert orphanName in {cam.get("name") for cam in res.get("cameras_relinked") or []}, \
    f"'{orphanName}' was not re-linked"

  for name, expected in test.archiveCams.items():
    cam = test.getCameraByName(name)
    assert cam.get("scene") == sceneUID, f"{name}: not attached to imported scene"
    assert cam.get("use_camera_pipeline") is True, f"{name}: use_camera_pipeline lost"
    assert cam.get("camera_pipeline") == pipeline, f"{name}: camera_pipeline lost"
    test.assertCalibrationMatchesArchive(cam, expected)

  result_recorder.success()
  return
