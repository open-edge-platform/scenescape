#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import re
import zipfile
import pytest
from scene_common.rest_client import RESTClient
from tests.functional import FunctionalTest

TEST_NAME = "NEX-T13967"


class SceneImportAPITest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute, zipFile, expected):
    super().__init__(testName, request, recordXMLAttribute)
    self.rest = RESTClient(self.params["resturl"], rootcert=self.params["rootcert"])
    assert self.rest.authenticate(self.params["user"], self.params["password"])

    self.expected = expected
    self.scene_name = self.params["scene"]
    self.zipFile = os.path.join("/workspace/tests/ui/test_media", zipFile)

    if expected == "1":  # EMPTY_ZIP
      self.create_empty_zip()
    elif expected in ["0", "3", "4"]:  # SUCCESS, SCENE_EXISTS, ORPHANED_CAMERA
      self.sceneData = self.read_json_from_zip()

  def create_empty_zip(self):
    with zipfile.ZipFile(self.zipFile, "w") as zf:
      pass


  def tolerant_camera_equivalence(self, cam1, cam2, tol=1e-9):
    """
    Returns True if two camera dictionaries are equivalent, allowing for small
    floating-point differences in numeric fields such as translation, rotation, etc.
    """
    for key in cam1:
      val1 = cam1[key]
      val2 = cam2.get(key)

      if isinstance(val1, list) and all(isinstance(x, float) for x in val1):
        if val1 != pytest.approx(val2, abs=tol):
          return False
      elif isinstance(val1, float):
        if val1 != pytest.approx(val2, abs=tol):
          return False
      else:
        if val1 != val2:
          return False
    return True

  def read_json_from_zip(self):
    with zipfile.ZipFile(self.zipFile, "r") as zip_ref:
      json_files = [f for f in zip_ref.namelist() if f.endswith(".json")]
      if not json_files:
        return None
      with zip_ref.open(json_files[0]) as json_file:
        return json.load(json_file)

  def is_error_response(self, response):
    for section in response.values():
      if isinstance(section, dict):
        for messages in section.values():
          if isinstance(messages, list) and messages:
            return True
    return False

  def get_scene_uid_by_name(self, name):
    scenes = self.rest.getScenes({"name": name}).get("results", [])
    assert scenes, f"Scene '{name}' not found"
    return scenes[0]["uid"]

  def cleanup_scene(self):
    # Delete scenes with the same name
    scenes = self.rest.getScenes({"name": self.sceneData["name"]}).get(
      "results", []
    )
    for scene in scenes:
      self.rest.deleteScene(scene["uid"])

    # Delete all cameras with the same names as in test data
    for cam in self.sceneData.get("cameras", []):
      cam_name = cam["name"]
      cameras = self.rest.getCameras({"name": cam_name}).get("results", [])
      for camera in cameras:
        self.rest.deleteCamera(camera["uid"])

    # Delete all sensors with the same sensor_id or name as in test data
    for sensor in self.sceneData.get("sensors", []):
      sensor_id = sensor.get("sensor_id") or sensor.get("name")
      sensors = self.rest.getSensors({"sensor_id": sensor_id}).get("results", [])
      for s in sensors:
        self.rest.deleteSensor(s["uid"])
      # Also try by name, in case sensor_id is not set
      sensors_by_name = self.rest.getSensors({"name": sensor.get("name")}).get(
        "results", []
      )
      for s in sensors_by_name:
        self.rest.deleteSensor(s["uid"])

    for cam in self.sceneData.get("cameras", []):
      cam_name = cam["name"]
      remaining = self.rest.getCameras({"name": cam_name}).get("results", [])

    for sensor in self.sceneData.get("sensors", []):
      sensor_id = sensor.get("sensor_id") or sensor.get("name")
      remaining = self.rest.getSensors({"sensor_id": sensor_id}).get(
        "results", []
      )

  def runTest(self):
    def is_error_response(response):
      for section in response.values():
        if isinstance(section, dict):
          for messages in section.values():
            if isinstance(messages, list) and messages:
              return True
      return False

    def get_scene_uid_by_name(name):
      scenes = self.rest.getScenes({"name": name}).get("results", [])
      assert scenes, f"Scene '{name}' not found"
      return scenes[0]["uid"]

    # Clean up before any import
    if self.expected in ["0", "3", "4"]:
      self.cleanup_scene()

    # First import
    res = self.rest.importScene(self.zipFile)

    # Parse orphaned cameras and sensors from response
    orphaned_cams = set()
    orphaned_sensors = set()
    if isinstance(res.get("cameras"), list):
      for cam_entry in res["cameras"]:
        if (
          isinstance(cam_entry, list)
          and isinstance(cam_entry[0], dict)
          and "name" in cam_entry[0]
        ):
          for name, msg in cam_entry[0].items():
            if isinstance(msg, list) and "orphaned camera" in msg[0]:
              match = re.search(
                r"orphaned camera with the name '([^']+)'", msg[0]
              )
              if match:
                orphaned_cams.add(match.group(1))
    if isinstance(res.get("sensors"), list):
      for sensor_entry in res["sensors"]:
        if (
          isinstance(sensor_entry, list)
          and isinstance(sensor_entry[0], dict)
          and "sensor_id" in sensor_entry[0]
        ):
          for sid, msg in sensor_entry[0].items():
            if isinstance(msg, list) and "already exists" in msg[0]:
              for s in self.sceneData.get("sensors", []):
                if (
                  s.get("sensor_id")
                  and s.get("sensor_id") not in orphaned_sensors
                ):
                  orphaned_sensors.add(s["sensor_id"])

    if orphaned_cams or orphaned_sensors:
      print(f"Orphaned cameras detected: {orphaned_cams}")
      print(f"Orphaned sensors detected: {orphaned_sensors}")

    if self.expected == "1":  # EMPTY_ZIP
      assert is_error_response(res), f"Expected failure for empty zip, got: {res}"
      print("✅ Empty zip correctly rejected.")

    elif self.expected == "2":  # INVALID_ZIP
      assert is_error_response(
        res
      ), f"Expected failure for invalid zip, got: {res}"
      print("✅ Invalid zip correctly rejected.")

    elif self.expected == "3":  # SCENE_EXISTS
      assert not is_error_response(res), f"Initial import failed: {res}"
      print("✅ Scene imported successfully.")

      # Second import (should fail)
      res_dup = self.rest.importScene(self.zipFile)
      assert is_error_response(
        res_dup
      ), f"Expected failure for duplicate scene, got: {res_dup}"
      print("✅ Duplicate scene correctly rejected.")

    elif self.expected == "4":  # ORPHANED_CAMERA
      assert not is_error_response(res), f"Import failed: {res}"
      scene_uid = get_scene_uid_by_name(self.sceneData["name"])

      cam_results = self.rest.getCameras({"scene": scene_uid}).get("results", [])
      sensor_results = self.rest.getSensors({"scene": scene_uid}).get(
        "results", []
      )

      # Exclude orphaned cameras/sensors from expected count
      expected_cams = [
        c
        for c in self.sceneData.get("cameras", [])
        if c["name"] not in orphaned_cams
      ]
      expected_sensors = [
        s
        for s in self.sceneData.get("sensors", [])
        if (s.get("sensor_id") or s.get("name")) not in orphaned_sensors
      ]

      print(f"Cameras linked to scene {scene_uid}: {cam_results}")
      print(f"Sensors linked to scene {scene_uid}: {sensor_results}")
      print(
        f"Expected camera count (excluding orphaned): {len(expected_cams)}, actual: {len(cam_results)}"
      )
      print(
        f"Expected sensor count (excluding orphaned): {len(expected_sensors)}, actual: {len(sensor_results)}"
      )

      if len(cam_results) != len(expected_cams):
        print(
          f"Camera count mismatch. Orphaned: {orphaned_cams}, Expected: {[c['name'] for c in expected_cams]}, Actual: {[c['name'] for c in cam_results]}"
        )
      if len(sensor_results) != len(expected_sensors):
        print(
          f"Sensor count mismatch. Orphaned: {orphaned_sensors}, Expected: {[s.get('sensor_id') or s.get('name') for s in expected_sensors]}, Actual: {[s.get('sensor_id') or s.get('name') for s in sensor_results]}"
        )

      assert len(cam_results) == len(expected_cams), "Camera count mismatch"
      assert len(sensor_results) == len(expected_sensors), "Sensor count mismatch"
      print("✅ Orphaned cameras and sensors correctly handled.")

    elif self.expected == "0":  # SUCCESS
      assert not is_error_response(res), f"Scene import failed: {res}"
      scene_uid = get_scene_uid_by_name(self.sceneData["name"])
      print("✅ Scene imported successfully.")
      self.validate_scene(self.sceneData, scene_uid)

    return True

  def validate_scene(self, scene, scene_uid):
    for cam in scene.get("cameras", []):
      res = self.rest.getCamera(cam["uid"])
      cam.pop("scene", None)
      cam.pop("distortion", None)
      res.pop("scene", None)
      assert self.tolerant_camera_equivalence(res, cam), f"Camera mismatch: {cam['uid']}"

    for sensor in scene.get("sensors", []):
      results = self.rest.getSensors({"name": sensor["name"]}).get("results", [])
      assert results, f"Sensor '{sensor['name']}' not found"
      res = results[0]
      for k in ("uid", "scene"):
        res.pop(k, None)
        sensor.pop(k, None)
      assert res == sensor, f"Sensor mismatch: {sensor['name']}"

    print("✅ Scene components validated.")

# Parametrized test entry point
@pytest.mark.parametrize(
  "zipFile, expected",
  [
    ("Retail-import.zip", "0"),  # SUCCESS
    ("Empty.zip", "1"),  # EMPTY_ZIP
    ("Retail-import.zip", "3"),  # SCENE_EXISTS
    ("Parent.zip", "0"),  # SUCCESS
    ("Invalid.zip", "2"),  # INVALID_ZIP
    ("Retail-import.zip", "4"),  # ORPHANED_CAMERA
    ("Intersection-Demo.zip", "0"),  # SUCCESS
  ],
)
def test_scene_import_api(request, record_xml_attribute, zipFile, expected):
  test = SceneImportAPITest(
    TEST_NAME, request, record_xml_attribute, zipFile, expected
  )
  assert test.runTest()
