#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

# The geospatial map calibration modules live in autocalibration/src, which is
# copied to the import path inside the container; add it on the host.
_AUTOCALIB_SRC = Path(__file__).resolve().parents[3] / "autocalibration" / "src"
if str(_AUTOCALIB_SRC) not in sys.path:
  sys.path.insert(0, str(_AUTOCALIB_SRC))

from geospatial_map_calibration import pose_from_look

MAP_SCALE = 10.0
MAP_SIZE_M = 100.0
IMAGE_W, IMAGE_H = 640, 360
INTRINSICS = [[400.0, 0.0, IMAGE_W / 2], [0.0, 400.0, IMAGE_H / 2], [0.0, 0.0, 1.0]]
GT_CAMERA = {"x": 50.0, "y": 30.0, "height": 6.5, "yaw": 75.0, "pitch": 10.0}


def _textured_map(seed=0):
  """! Asymmetric synthetic ortho map: random coloured blobs and bars. """
  rng = np.random.default_rng(seed)
  size = int(MAP_SIZE_M * MAP_SCALE)
  img = np.full((size, size, 3), 90, np.uint8)
  for _ in range(500):
    center = tuple(int(v) for v in rng.integers(0, size, 2))
    color = [int(v) for v in rng.integers(20, 236, 3)]
    cv2.circle(img, center, int(rng.integers(8, 40)), color, -1)
  for _ in range(60):
    p0 = tuple(int(v) for v in rng.integers(0, size, 2))
    p1 = tuple(int(v) for v in rng.integers(0, size, 2))
    color = [int(v) for v in rng.integers(20, 236, 3)]
    cv2.line(img, p0, p1, color, int(rng.integers(3, 12)))
  return cv2.GaussianBlur(img, (5, 5), 0)


def render_camera(map_bgr, pose, K=INTRINSICS, width=IMAGE_W, height=IMAGE_H):
  """! Renders a pinhole view of the flat map from the given world-from-camera pose. """
  K = np.asarray(K, dtype=np.float64)
  us, vs = np.meshgrid(np.arange(width, dtype=np.float64), np.arange(height, dtype=np.float64))
  pix = np.stack([us.ravel(), vs.ravel(), np.ones(us.size)])
  rays = pose[:3, :3] @ (np.linalg.inv(K) @ pix)
  origin = pose[:3, 3]
  with np.errstate(divide="ignore", invalid="ignore"):
    t = -origin[2] / rays[2]
  valid = rays[2] < -1e-6
  gx = origin[0] + t * rays[0]
  gy = origin[1] + t * rays[1]
  map_x = np.where(valid, gx * MAP_SCALE, -1).reshape(height, width).astype(np.float32)
  map_y = np.where(valid, map_bgr.shape[0] - gy * MAP_SCALE, -1).reshape(height, width).astype(np.float32)
  return cv2.remap(map_bgr, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


@pytest.fixture(scope="module")
def textured_map():
  return _textured_map()


@pytest.fixture(scope="module")
def gt_pose():
  return pose_from_look(GT_CAMERA["x"], GT_CAMERA["y"], GT_CAMERA["height"],
                        GT_CAMERA["yaw"], GT_CAMERA["pitch"])


@pytest.fixture(scope="module")
def camera_frame(textured_map, gt_pose):
  return render_camera(textured_map, gt_pose)


@pytest.fixture
def map_file(tmp_path, textured_map):
  path = tmp_path / "ortho.png"
  cv2.imwrite(str(path), textured_map)
  return str(path)


@pytest.fixture
def uniform_map_file(tmp_path):
  path = tmp_path / "uniform.png"
  size = int(MAP_SIZE_M * MAP_SCALE)
  cv2.imwrite(str(path), np.full((size, size, 3), 128, np.uint8))
  return str(path)


@pytest.fixture
def scene_factory():
  def _make(map_path, scale=MAP_SCALE, map_processed=None):
    return SimpleNamespace(id="scene-1", name="geo", map=map_path, scale=scale,
                           map_processed=map_processed, camera_calibration="Markerless",
                           polycam_data=None)
  return _make


@pytest.fixture
def data_interface():
  return Mock()


@pytest.fixture
def no_vanishing_point(monkeypatch):
  """! Forces the pitch fallback so tests do not depend on line detection of synthetic frames. """
  import geospatial_map_calibration
  monkeypatch.setattr(geospatial_map_calibration, "estimate_vanishing_point", lambda frame: None)


def encode_image(image):
  ok, buf = cv2.imencode(".png", image)
  assert ok
  return base64.b64encode(buf.tobytes()).decode("ascii")
