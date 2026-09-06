# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit checks for LiDAR bbox yaw quaternion packing."""

import importlib.util
import math
from pathlib import Path

import pytest

_PUBLISHER = (
  Path(__file__).resolve().parents[3]
  / "sample_data"
  / "lidar_intersection"
  / "lidar_publisher.py"
)


def _load_lidar_publisher():
  spec = importlib.util.spec_from_file_location("lidar_publisher_under_test", _PUBLISHER)
  module = importlib.util.module_from_spec(spec)
  # Avoid executing MQTT/GStreamer side effects: only load by running file is OK
  # because module-level code is imports + constants (no connect).
  spec.loader.exec_module(module)
  return module


@pytest.fixture(scope="module")
def lidar_publisher():
  return _load_lidar_publisher()


@pytest.fixture(scope="module")
def bbox3d_to_quaternion(lidar_publisher):
  return lidar_publisher.bbox3d_to_quaternion


@pytest.mark.parametrize("yaw", [
  -math.pi,
  -math.pi / 2.0,
  -0.5,
  0.0,
  0.5,
  math.pi / 2.0,
  math.pi - 1e-3,
])
def test_bbox3d_to_quaternion_is_xyzw_y_rotation_matching_velodyne_yaw(bbox3d_to_quaternion, yaw):
  q = bbox3d_to_quaternion(yaw)
  assert len(q) == 4
  assert abs(q[0]) < 1e-9 and abs(q[2]) < 1e-9
  # SceneScape / scipy xyzw: conjugate of Velodyne Rz is Ry(-yaw) packing [0,-sin,0,cos]
  recovered = -2.0 * math.atan2(q[1], q[3])
  recovered = (recovered + math.pi) % (2 * math.pi) - math.pi
  expected = (yaw + math.pi) % (2 * math.pi) - math.pi
  assert recovered == pytest.approx(expected, abs=1e-5)


def test_bbox3d_to_quaternion_not_legacy_w_first_packing(bbox3d_to_quaternion):
  """Legacy bug packed [qw, -qz, 0, 0]; valid xyzw for yaw=0 is identity-ish [0,0,0,1]."""
  q = bbox3d_to_quaternion(0.0)
  assert q[3] == pytest.approx(1.0 - 1e-7, abs=1e-6) or q[3] == pytest.approx(1.0, abs=1e-6)
  assert abs(q[0]) < 1e-6 and abs(q[1]) < 1e-6 and abs(q[2]) < 1e-6


def test_build_lidar_message_publishes_raw_detector_yaw(lidar_publisher):
  """Publisher must not apply modality-specific yaw heuristics."""
  raw = {
    "objects": [{
      "label": "vehicle",
      "confidence": 0.9,
      "bbox_3d": {"x": 1.0, "y": 0.0, "z": 0.0, "l": 4.0, "w": 2.0, "h": 1.5, "yaw": 0.75},
    }],
  }
  msg = lidar_publisher.build_lidar_message(raw, None, 10.0)
  q = msg["objects"]["vehicle"][0]["rotation"]
  recovered = -2.0 * math.atan2(q[1], q[3])
  recovered = (recovered + math.pi) % (2 * math.pi) - math.pi
  assert recovered == pytest.approx(0.75, abs=1e-5)
