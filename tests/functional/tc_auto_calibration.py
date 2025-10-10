#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import os
import base64
import json
import requests
import pytest
from pupil_apriltags import Detector
import cv2
import numpy as np
import random

from tests.functional import FunctionalTest
from scene_common import log
from scene_common.rest_client import RESTClient

TEST_NAME = "NEX-T10405"
MAX_WAIT = 5
BASE_URL = "https://camcalibration.scenescape.intel.com:8443"
VERIFY_CERT = "/run/secrets/certs/scenescape-ca.pem"

class AutoCalibration(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute, nTags, randomSelect, expected, intrinsics=None):
    super().__init__(testName, request, recordXMLAttribute)
    self.scene_name = "Queuing"
    self.scene_id = '302cf49a-97ec-402d-a324-c5077b280b7b'
    self.camera_id = "atag-qcam1"
    self.frame = "/workspace/tests/ui/test_media/atag-qcam1-frame.png"
    self.exitCode = 1
    self.nTags = nTags
    self.randomSelect = randomSelect
    self.expected = expected
    self.sceneRegistered = False
    self.intrinsics = intrinsics

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, (res.errors)

  def obscure_detected_apriltag(self, image_path, tag_family="tag36h11", n_tags=1, random_select=False):
    img = cv2.imread(image_path)
    if img is None:
      raise ValueError(f"Failed to load image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    detector = Detector(
      families=tag_family,
      nthreads=1,
      quad_decimate=1.0,
      quad_sigma=0.0,
      refine_edges=True,
      decode_sharpening=0.25,
      debug=False
    )

    tags = detector.detect(gray)
    if not tags:
      print("No AprilTags detected — skipping obscuration.")
      _, buf = cv2.imencode(".png", img)
      return base64.b64encode(buf).decode("utf-8")

    print(f"Detected {len(tags)} AprilTags")
    if n_tags > len(tags):
      n_tags = len(tags)

    selected = random.sample(tags, n_tags) if random_select else tags[:n_tags]
    for i, tag in enumerate(selected):
      corners = np.int32(tag.corners)
      x1, y1 = np.min(corners, axis=0)
      x2, y2 = np.max(corners, axis=0)

      pad = 10
      x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
      x2, y2 = min(img.shape[1], x2 + pad), min(img.shape[0], y2 + pad)

      cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), -1)
      print(f"Obscured tag {i+1}: ({x1},{y1}) - ({x2},{y2})")

    _, buf = cv2.imencode(".png", img)
    img_b64 = base64.b64encode(buf).decode("utf-8")
    return img_b64

  def get_status(self):
    url = f"{BASE_URL}/v1/status"
    try:
      r = requests.get(url, verify=VERIFY_CERT)
      print("Service status:", r.json())
      return r.json()
    except Exception as e:
      print("Error fetching service status:", e)
      return None

  def register_scene(self, method="POST", poll_interval=5, timeout=60):
    url = f"{BASE_URL}/v1/scenes/{self.scene_id}/registration"
    try:
      if method.upper() == "POST":
        r = requests.post(url, json={}, verify=VERIFY_CERT)
        print(f"POST scene registration [{self.scene_name}]:", r.status_code, r.text)
      else:
        r = requests.get(url, verify=VERIFY_CERT)
        print(f"GET scene registration status [{self.scene_name}]:", r.status_code, r.text)

      data = r.json()

      if method.upper() == "POST" and data.get("status") == "registering":
        print(f"Scene '{self.scene_name}' registering... polling for completion")
        start_time = time.time()

        while time.time() - start_time < timeout:
          time.sleep(poll_interval)
          try:
            poll_resp = requests.get(url, verify=VERIFY_CERT)
            poll_data = poll_resp.json()
            print("Poll result:", poll_data)
            if poll_data.get("status") == "success":
              print("Scene registration complete:", poll_data)
              return poll_data
            elif poll_data.get("status") == "error":
              print("Scene registration failed:", poll_data)
              return poll_data
          except Exception as pe:
            print("Error polling scene status:", pe)

        print("Scene registration polling timed out")
        return data
      return data

    except Exception as e:
      print("Error registering scene:", e)
      return None

  def start_calibration(self, image_b64, intrinsics=None):
    url = f"{BASE_URL}/v1/cameras/{self.camera_id}/calibration"
    payload = {"image": image_b64}

    if intrinsics is not None:
      payload["intrinsics"] = intrinsics
    try:
      r = requests.post(url, json=payload, verify=VERIFY_CERT)
      print("Calibration start:", r.status_code, r.text)
      return r.json()
    except Exception as e:
      print("Error starting calibration:", e)
      return None

  def get_calibration_status(self):
    url = f"{BASE_URL}/v1/cameras/{self.camera_id}/calibration"
    try:
      r = requests.get(url, verify=VERIFY_CERT)
      data = r.json()
      print("Calibration status:", r.status_code, data)
      return data
    except Exception as e:
      print("Error checking calibration:", e)
      return None

  def runAutoCalibration(self):
    time.sleep(MAX_WAIT)
    status = self.get_status()
    if not status or status.get("status") != "running":
      print("Service not ready, aborting")
      return

    if not self.sceneRegistered:
      reg = self.register_scene(method="POST")
      self.sceneRegistered = True
      assert reg
      assert reg['status'] == "success"
      print('registering status: ', reg)

    if self.nTags > 0:
      img_b64 = self.obscure_detected_apriltag(self.frame, n_tags=self.nTags, random_select=self.randomSelect)
    else:
      with open(self.frame, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    start = self.start_calibration(img_b64, self.intrinsics)
    if not start or start.get("status") not in ("calibrating", "success", "pending"):
      print("Failed to start calibration:", start)
      return

    # Poll for result
    for _ in range(12):
      time.sleep(MAX_WAIT)
      result = self.get_calibration_status()
      assert result
      if self.expected == result['status']:
        self.exitCode = 0
      if result['status'] == 'success':
        assert result['calibration_points_2d']
        assert result['calibration_points_3d']
        assert result['cameraId']
        assert result['camera_frustum']
        assert result['quaternion']
        assert result['sceneId']
        assert result['translation']
        break
    return

@pytest.mark.parametrize(
  "n_tags, random_select, expect_success, intrinsics",
  [
    (0, False, "success", [[905, 0, 640], [0, 905, 360], [0, 0, 1]]),
    (2, False, "success", [[905, 0, 640], [0, 905, 360], [0, 0, 1]]),
    (1, True, "success", None),
    (6, True,  "pending", [[905, 0, 640], [0, 905, 360], [0, 0, 1]]),
  ]
)
def test_auto_calibration(request, record_xml_attribute, n_tags, random_select, expect_success, intrinsics):
  test = AutoCalibration(TEST_NAME, request, record_xml_attribute, n_tags, random_select, expect_success, intrinsics=intrinsics)
  test.runAutoCalibration()
  assert test.exitCode == 0
  return test.exitCode

def main():
  return test_auto_calibration(None, None)

if __name__ == "__main__":
  os._exit(main() or 0)
