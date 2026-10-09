# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from threading import Lock

import numpy as np

import atag_camera_calibration_controller as calibration
from auto_camera_calibration_api import CameraCalibrationApi


def _generate_calibration(monkeypatch, points_3d, camera_translation, tag_size=0.2,
                          map_name="scene.png", reprojection_offset=0, mesh_scale=(1, 1, 1)):
  scene = SimpleNamespace(id="scene-id", map=map_name, name="test-scene",
                          apriltag_size=tag_size, mesh_scale=mesh_scale)
  intrinsics = np.array([[500., 0., 320.], [0., 500., 240.], [0., 0., 1.]])
  camera_pose = np.eye(4)
  camera_pose[2, 3] = -2
  points_2d, _ = calibration.cv2.projectPoints(np.asarray(points_3d, dtype=float),
                                                np.zeros(3), np.array([0., 0., 2.]),
                                                intrinsics, None)
  points_2d = (points_2d.reshape(-1, 2) + reprojection_offset).tolist()
  camera_calibration = SimpleNamespace(
      result_data_3d={str(index): point for index, point in enumerate(points_3d)},
      apriltags_2d_data={str(index): point for index, point in enumerate(points_3d)},
      tag_size=tag_size,
      find_apriltags_in_frame=lambda image, store: None,
      get_camera_pose_in_scene=lambda: camera_pose,
      get_camera_frustum=lambda: [],
      get_point_correspondences=lambda: (points_3d, points_2d),
  )
  controller = object.__new__(calibration.ApriltagCameraCalibrationController)
  controller.cam_calib_objs = {scene.id: camera_calibration}
  controller.frame_count = {}
  monkeypatch.setattr(controller, "decode_image", lambda image: np.zeros((1, 1, 3)))
  monkeypatch.setattr(calibration, "getPoseMatrix",
                      lambda scene, rotation: np.diag([*scene.mesh_scale, 1.0]))
  monkeypatch.setattr(calibration, "CameraIntrinsics", lambda intrinsics: intrinsics)
  monkeypatch.setattr(
      calibration,
      "CameraPose",
      lambda pose, intrinsics: SimpleNamespace(quaternion_rotation=np.array([0, 0, 0, 1])),
  )
  transform = np.eye(4)
  transform[:3, 3] = camera_translation
  monkeypatch.setattr(
      calibration,
      "convertToTransformMatrix",
      lambda scene_matrix, quaternion, translation: transform,
  )

  return controller.generate_calibration(
      scene, intrinsics, {"id": "camera-id", "image": b"image"})


def test_generate_calibration_accepts_well_spread_tags(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2])

  assert result["status"] == "success"
  assert result["spread_ratio"] >= calibration.MIN_PNP_SPREAD_RATIO


def test_generate_calibration_uses_map_spread_when_scene_scale_flattens_tags(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2],
                                 map_name="scene.glb", mesh_scale=(1, 1, 0.001))

  assert result["status"] == "success"
  assert result["spread_ratio"] >= calibration.MIN_PNP_SPREAD_RATIO
  assert result["calibration_points_3d"][-1] == [0, 0, 0.001]


def test_generate_calibration_uses_map_spread_when_scene_scale_stretches_tags(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0.001]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2],
                                 map_name="scene.glb", mesh_scale=(1, 1, 1000))

  assert result["status"] == "error"
  assert "coplanar" in result["message"]
  assert result["spread_ratio"] < calibration.MIN_PNP_SPREAD_RATIO


def test_generate_calibration_accepts_planar_image_tags(monkeypatch, result_data):
  points_3d = list(result_data.values())

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2])

  assert result["status"] == "success"
  assert result["spread_ratio"] < calibration.MIN_PNP_SPREAD_RATIO


def test_generate_calibration_rejects_collinear_image_tags(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2])

  assert result["status"] == "error"
  assert "collinear" in result["message"]
  assert result["spread_ratio"] < calibration.MIN_PNP_SPREAD_RATIO


def test_generate_calibration_rejects_bad_planar_reprojection(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2], reprojection_offset=10)

  assert result["status"] == "error"
  assert "reprojection error" in result["message"]


def test_generate_calibration_rejects_coplanar_mesh_tags(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, 2], map_name="scene.glb")

  assert result["status"] == "error"
  assert "coplanar" in result["message"]


def test_generate_calibration_rejects_camera_far_below_tags(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, -0.2])

  assert result["status"] == "error"
  assert "below the AprilTags" in result["message"]
  assert result["translation"][2] == -0.2


def test_camera_below_tag_tolerance_scales_with_tag_size(monkeypatch):
  points_3d = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]

  result = _generate_calibration(monkeypatch, points_3d, [0, 0, -0.15], tag_size=0.4)

  assert result["status"] == "success"


def test_calibration_status_exposes_spread_ratio():
  scene = SimpleNamespace(id="scene-id", camera_calibration="AprilTag")
  context = SimpleNamespace(
      calibration_data_interface=SimpleNamespace(scene_camera_with_id=lambda camera_id: scene),
      calibration_thread_lock=Lock(),
      calibration_results={"camera-id": {"status": "success", "spread_ratio": 0.25}},
  )
  api = CameraCalibrationApi(context)

  response = api.app.test_client().get("/v1/cameras/camera-id/calibration")

  assert response.status_code == 200
  assert response.get_json()["spread_ratio"] == 0.25
