# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for mock_manager.py.

All tests run without Docker.  The HTTP-server tests use a real HTTPServer on
an ephemeral port so they exercise the full request/response path.
"""

import json
import math
import sys
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from harnesses.black_box_harness.mock_manager import (
    _DISTORTION_KEYS,
    _MAX_COPLANAR_DETERMINANT,
    _are_coplanar,
    _build_rest_scene,
    _calculate_determinant,
    _compute_extrinsics,
    _distortion_to_array,
    _pose_mat_to_extrinsics,
    MockManagerHandler,
    run as mock_manager_run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_camera_scene_config():
  """Minimal two-camera scene config identical to the Unity dataset."""
  return {
      "name": "TestScene",
      "uid": "test-scene-uid",
      "map": "map.png",
      "scale": 38.1,
      "sensors": {
          "Cam_x1_0": {
              "intrinsics": [964.24, 964.63, 400.0, 300.0],
              "distortion": None,
              "width": 800,
              "height": 600,
              "camera points": [[201, 119], [592, 118], [781, 579], [2, 579]],
              "map points": [[3, 15, 0], [10, 15, 0], [10, 5, 0], [3, 5, 0]],
          },
          "Cam_x2_0": {
              "intrinsics": [964.24, 964.63, 400.0, 300.0],
              "distortion": None,
              "width": 800,
              "height": 600,
              "camera points": [[2, 447], [570, 187], [135, 187], [664, 445]],
              "map points": [[10, 9, 0], [0, 0, 0], [10, 0, 0], [0, 9, 0]],
          },
      },
  }


@pytest.fixture
def rest_server(two_camera_scene_config):
  """Start a real HTTPServer on an ephemeral port; yield base URL; stop after test."""
  from harnesses.black_box_harness.mock_manager import _build_rest_scene
  scene = _build_rest_scene(two_camera_scene_config)
  server = HTTPServer(("127.0.0.1", 0), MockManagerHandler)
  server.scene = scene
  port = server.server_address[1]
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  yield f"http://127.0.0.1:{port}"
  server.shutdown()


# ---------------------------------------------------------------------------
# _distortion_to_array
# ---------------------------------------------------------------------------

class TestDistortionToArray:
  def test_none_returns_zeros(self):
    arr = _distortion_to_array(None)
    assert arr.shape == (14,)
    assert np.all(arr == 0.0)

  def test_list_padded_to_14(self):
    arr = _distortion_to_array([0.1, 0.2, 0.0, 0.0, 0.05])
    assert arr.shape == (14,)
    assert arr[0] == pytest.approx(0.1)
    assert arr[4] == pytest.approx(0.05)
    assert arr[5] == pytest.approx(0.0)

  def test_dict_mapped_by_key_order(self):
    dist_dict = {"k1": 0.1, "k2": 0.2, "p1": 0.01, "p2": 0.02, "k3": 0.05}
    arr = _distortion_to_array(dist_dict)
    assert arr.shape == (14,)
    assert arr[0] == pytest.approx(0.1)   # k1
    assert arr[1] == pytest.approx(0.2)   # k2
    assert arr[2] == pytest.approx(0.01)  # p1
    assert arr[3] == pytest.approx(0.02)  # p2
    assert arr[4] == pytest.approx(0.05)  # k3

  def test_dict_missing_keys_default_to_zero(self):
    arr = _distortion_to_array({"k1": 0.5})
    assert arr[0] == pytest.approx(0.5)
    assert arr[1] == pytest.approx(0.0)

  def test_14_key_dict_all_preserved(self):
    dist_dict = {k: float(i) for i, k in enumerate(_DISTORTION_KEYS)}
    arr = _distortion_to_array(dist_dict)
    for i, k in enumerate(_DISTORTION_KEYS):
      assert arr[i] == pytest.approx(float(i)), f"key {k} at index {i} mismatch"


# ---------------------------------------------------------------------------
# _calculate_determinant / _are_coplanar
# ---------------------------------------------------------------------------

class TestCoplanarity:
  def test_four_coplanar_z0_points(self):
    points = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    assert abs(_calculate_determinant(points)) <= _MAX_COPLANAR_DETERMINANT
    assert _are_coplanar(points)

  def test_four_non_coplanar_points(self):
    points = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert abs(_calculate_determinant(points)) > _MAX_COPLANAR_DETERMINANT
    assert not _are_coplanar(points)

  def test_five_coplanar_points(self):
    points = [[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 1, 0], [1, 1, 0]]
    assert _are_coplanar(points)

  def test_five_non_coplanar_points(self):
    points = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]]
    assert not _are_coplanar(points)

  def test_six_or_more_always_coplanar_result(self):
    """arePointsCoplanar returns True for >=6 points (no check performed)."""
    points = [[i, 0, 0] for i in range(6)]
    assert _are_coplanar(points)


# ---------------------------------------------------------------------------
# _pose_mat_to_extrinsics
# ---------------------------------------------------------------------------

class TestPoseMatToExtrinsics:
  def test_identity_translation_is_origin(self):
    mat = np.eye(4)
    ext = _pose_mat_to_extrinsics(mat)
    assert ext["translation"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-9)

  def test_known_translation(self):
    mat = np.eye(4)
    mat[0, 3] = 1.0
    mat[1, 3] = 2.0
    mat[2, 3] = 3.0
    ext = _pose_mat_to_extrinsics(mat)
    assert ext["translation"] == pytest.approx([1.0, 2.0, 3.0], abs=1e-9)

  def test_scale_unity_for_identity(self):
    ext = _pose_mat_to_extrinsics(np.eye(4))
    assert ext["scale"] == pytest.approx([1.0, 1.0, 1.0], abs=1e-9)

  def test_euler_zero_for_identity(self):
    ext = _pose_mat_to_extrinsics(np.eye(4))
    assert ext["rotation"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-9)

  def test_returns_plain_python_floats(self):
    ext = _pose_mat_to_extrinsics(np.eye(4))
    for v in ext["translation"] + ext["rotation"] + ext["scale"]:
      assert isinstance(v, float), f"Expected float, got {type(v)}"

  def test_json_serializable(self):
    ext = _pose_mat_to_extrinsics(np.eye(4))
    # Should not raise
    json.dumps(ext)


# ---------------------------------------------------------------------------
# _compute_extrinsics
# ---------------------------------------------------------------------------

class TestComputeExtrinsics:
  """Tests use the metric dataset camera configs (4 coplanar points, z=0)."""

  @pytest.fixture
  def cam1_args(self):
    return dict(
        cam_pts=[[201, 119], [592, 118], [781, 579], [2, 579]],
        map_pts=[[3, 15, 0], [10, 15, 0], [10, 5, 0], [3, 5, 0]],
        intrinsics=[964.24, 964.63, 400.0, 300.0],
        distortion=None,
    )

  def test_returns_dict_with_required_keys(self, cam1_args):
    ext = _compute_extrinsics(**cam1_args)
    assert ext is not None
    assert set(ext.keys()) == {"translation", "rotation", "scale"}

  def test_translation_is_3_floats(self, cam1_args):
    ext = _compute_extrinsics(**cam1_args)
    assert len(ext["translation"]) == 3
    for v in ext["translation"]:
      assert isinstance(v, float)

  def test_rotation_is_3_floats(self, cam1_args):
    ext = _compute_extrinsics(**cam1_args)
    assert len(ext["rotation"]) == 3

  def test_scale_approximately_unity(self, cam1_args):
    """Orthographic projection → scale should be ~1 on all axes."""
    ext = _compute_extrinsics(**cam1_args)
    assert ext["scale"] == pytest.approx([1.0, 1.0, 1.0], abs=0.01)

  def test_json_serializable(self, cam1_args):
    ext = _compute_extrinsics(**cam1_args)
    json.dumps(ext)

  def test_returns_none_for_insufficient_points(self):
    """Fewer than 4 points → solvePnP fails → None returned."""
    ext = _compute_extrinsics(
        cam_pts=[[0, 0], [1, 0]],
        map_pts=[[0, 0, 0], [1, 0, 0]],
        intrinsics=[500.0, 500.0, 320.0, 240.0],
    )
    assert ext is None

  def test_distortion_dict_accepted(self, cam1_args):
    cam1_args["distortion"] = {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0}
    ext = _compute_extrinsics(**cam1_args)
    assert ext is not None

  def test_2d_map_points_accepted(self, cam1_args):
    """map_pts with z omitted (2-column) should auto-extend with z=0."""
    cam1_args["map_pts"] = [[3, 15], [10, 15], [10, 5], [3, 5]]
    ext = _compute_extrinsics(**cam1_args)
    assert ext is not None


# ---------------------------------------------------------------------------
# _build_rest_scene
# ---------------------------------------------------------------------------

class TestBuildRestScene:
  def test_structure(self, two_camera_scene_config):
    scene = _build_rest_scene(two_camera_scene_config)
    assert scene["uid"] == "test-scene-uid"
    assert scene["name"] == "TestScene"
    assert isinstance(scene["cameras"], list)
    assert len(scene["cameras"]) == 2

  def test_camera_required_fields(self, two_camera_scene_config):
    scene = _build_rest_scene(two_camera_scene_config)
    for cam in scene["cameras"]:
      for field in ("uid", "name", "intrinsics", "distortion", "resolution",
                    "camera points", "map points", "extrinsics"):
        assert field in cam, f"Missing field '{field}' in camera {cam.get('uid')}"

  def test_intrinsics_dict_format(self, two_camera_scene_config):
    scene = _build_rest_scene(two_camera_scene_config)
    for cam in scene["cameras"]:
      intr = cam["intrinsics"]
      assert set(intr.keys()) == {"fx", "fy", "cx", "cy"}

  def test_distortion_has_all_14_keys(self, two_camera_scene_config):
    scene = _build_rest_scene(two_camera_scene_config)
    for cam in scene["cameras"]:
      assert set(cam["distortion"].keys()) == set(_DISTORTION_KEYS)

  def test_extrinsics_computed_not_zeros(self, two_camera_scene_config):
    """Both cameras have enough points — extrinsics should not be all zeros."""
    scene = _build_rest_scene(two_camera_scene_config)
    for cam in scene["cameras"]:
      t = cam["extrinsics"]["translation"]
      assert any(abs(v) > 0.01 for v in t), \
          f"Camera {cam['uid']} has zero translation — extrinsics computation failed"

  def test_fallback_uid_from_name(self):
    cfg = {
        "name": "FallbackScene",
        "sensors": {},
    }
    scene = _build_rest_scene(cfg)
    assert scene["uid"] == "FallbackScene"

  def test_fully_json_serializable(self, two_camera_scene_config):
    scene = _build_rest_scene(two_camera_scene_config)
    json.dumps(scene)  # must not raise TypeError for np.float64 etc.


# ---------------------------------------------------------------------------
# MockManagerHandler — HTTP endpoints
# ---------------------------------------------------------------------------

class TestMockManagerHTTP:
  def _get(self, base_url, path):
    host_port = base_url.replace("http://", "")
    host, port = host_port.rsplit(":", 1)
    conn = HTTPConnection(host, int(port))
    conn.request("GET", path)
    resp = conn.getresponse()
    body = json.loads(resp.read())
    conn.close()
    return resp.status, body

  def _post(self, base_url, path, body=None):
    host_port = base_url.replace("http://", "")
    host, port = host_port.rsplit(":", 1)
    data = json.dumps(body or {}).encode()
    conn = HTTPConnection(host, int(port))
    conn.request("POST", path, body=data,
                 headers={"Content-Type": "application/json",
                          "Content-Length": str(len(data))})
    resp = conn.getresponse()
    body_data = json.loads(resp.read())
    conn.close()
    return resp.status, body_data

  def test_post_auth_returns_token(self, rest_server):
    status, body = self._post(rest_server, "/api/v1/auth")
    assert status == 200
    assert "token" in body

  def test_get_scenes_returns_scene_list(self, rest_server):
    status, body = self._get(rest_server, "/api/v1/scenes")
    assert status == 200
    assert "results" in body
    assert len(body["results"]) == 1
    assert body["results"][0]["uid"] == "test-scene-uid"

  def test_get_scenes_child_returns_empty(self, rest_server):
    status, body = self._get(rest_server, "/api/v1/scenes/child")
    assert status == 200
    assert body["results"] == []

  def test_get_assets_returns_empty(self, rest_server):
    status, body = self._get(rest_server, "/api/v1/assets")
    assert status == 200
    assert body["results"] == []

  def test_get_camera_returns_correct_camera(self, rest_server):
    status, body = self._get(rest_server, "/api/v1/camera/Cam_x1_0")
    assert status == 200
    assert body["uid"] == "Cam_x1_0"
    assert "extrinsics" in body
    assert "camera points" in body

  def test_get_camera_not_found_returns_404(self, rest_server):
    status, body = self._get(rest_server, "/api/v1/camera/no-such-cam")
    assert status == 404

  def test_post_camera_returns_200(self, rest_server):
    status, body = self._post(rest_server, "/api/v1/camera/Cam_x1_0",
                               {"extrinsics": {"translation": [1, 2, 3]}})
    assert status == 200

  def test_get_unknown_path_returns_404(self, rest_server):
    status, body = self._get(rest_server, "/api/v1/unknown")
    assert status == 404

  def test_trailing_slash_normalised(self, rest_server):
    """Trailing slash on /api/v1/scenes/ is handled identically."""
    status, body = self._get(rest_server, "/api/v1/scenes/")
    assert status == 200
    assert "results" in body
