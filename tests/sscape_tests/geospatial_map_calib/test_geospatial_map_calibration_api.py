#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

pytest.importorskip("flask_socketio")
pytest.importorskip("open3d")

from conftest import INTRINSICS, encode_image

from auto_camera_calibration_api import CameraCalibrationApi
from geospatial_map_calibration_controller import GeospatialMapCalibrationController

CAMERA_ID = "cam1"
URL = f"/v1/cameras/{CAMERA_ID}/calibration"


@pytest.fixture
def image_b64():
  return encode_image(np.full((32, 32, 3), 100, np.uint8))


def _client(strategy):
  context = Mock()
  context.calibration_data_interface.scene_camera_with_id.return_value = SimpleNamespace(
    id="scene-1", camera_calibration="Markerless")
  context.strategy_for_scene.return_value = strategy
  context.calibration_thread_lock.locked.return_value = False
  context.calibration_results = {}
  api = CameraCalibrationApi(calibrationContext=context)
  return api.app.test_client(), context


@pytest.fixture
def geo_client():
  return _client(GeospatialMapCalibrationController(calibration_data_interface=Mock()))


def test_post_with_prior_starts_calibration(geo_client, image_b64):
  client, context = geo_client
  prior = {"mapPoint": [10.5, 20], "heading": 90, "height": 6.5}
  resp = client.post(URL, json={"image": image_b64, "intrinsics": INTRINSICS, "prior": prior})
  assert resp.status_code == 202
  frame_data = context.calibrate_camera_thread_wrapper.call_args.args[3]
  assert frame_data["prior"] == prior


def test_post_without_prior_starts_calibration(geo_client, image_b64):
  client, context = geo_client
  resp = client.post(URL, json={"image": image_b64, "intrinsics": INTRINSICS})
  assert resp.status_code == 202
  assert "prior" not in context.calibrate_camera_thread_wrapper.call_args.args[3]


@pytest.mark.parametrize("prior", [
  "north",
  {"mapPoint": [1.0]},
  {"mapPoint": [1.0, "2"]},
  {"mapPoint": [1.0, float("inf")]},
  {"heading": True},
  {"heading": "90"},
  {"height": 0},
  {"height": 10000},
  {"yaw": 90},
])
def test_post_invalid_prior_rejected(geo_client, image_b64, prior):
  client, context = geo_client
  resp = client.post(URL, json={"image": image_b64, "intrinsics": INTRINSICS, "prior": prior})
  assert resp.status_code == 400
  context.calibrate_camera_thread_wrapper.assert_not_called()


def test_post_prior_rejected_for_non_map_strategy(image_b64):
  client, context = _client(Mock())
  resp = client.post(URL, json={"image": image_b64, "intrinsics": INTRINSICS, "prior": {"heading": 0}})
  assert resp.status_code == 400
  assert "geospatial" in resp.get_json()["message"]
  context.calibrate_camera_thread_wrapper.assert_not_called()


def test_get_needs_prior_result(geo_client):
  client, context = geo_client
  candidates = [{"yaw_deg": 0.0, "score": 0.3, "map_point": [1.0, 2.0]}]
  context.calibration_results[CAMERA_ID] = {
    "status": "needs_prior", "message": "Ambiguous heading",
    "candidates": candidates, "confidence": {"needs_prior": True}}
  body = client.get(URL).get_json()
  assert body["status"] == "needs_prior"
  assert body["candidates"] == candidates
  assert body["confidence"] == {"needs_prior": True}
  assert "quaternion" not in body


def test_get_success_result(geo_client):
  client, context = geo_client
  context.calibration_results[CAMERA_ID] = {
    "status": "success", "message": "ok", "quaternion": [0.0, 0.0, 0.0, 1.0],
    "translation": [1.0, 2.0, 6.0], "calibration_points_2d": [[1.0, 2.0]],
    "calibration_points_3d": [[3.0, 4.0, 0.0]], "confidence": {"needs_prior": False}}
  body = client.get(URL).get_json()
  assert body["status"] == "success"
  assert body["translation"] == [1.0, 2.0, 6.0]
  assert body["calibration_points_3d"] == [[3.0, 4.0, 0.0]]
  assert body["confidence"] == {"needs_prior": False}
