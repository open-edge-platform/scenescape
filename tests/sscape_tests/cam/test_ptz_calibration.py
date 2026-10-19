# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import Mock, patch

import numpy as np
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager.models import Cam, PubSubACL, Scene, sendUpdateCommand
from manager.ptz_calibration import PTZCalibrationError, axis_travel_deg, validate_ptz_calibration
from manager.serializers import CamSerializer
from scene_common.mqtt import PubSub

REPO_ROOT = Path(__file__).resolve().parents[3]
USER_ACCESS_CONFIG = REPO_ROOT / "manager" / "config" / "user_access_config.json"


PTZ_CALIBRATION = {
  "parameterization_version": "v1",
  "calibration_version": "cam1-v1",
  "position_space": {
    "uri": "urn:onvif:position-space",
    "pan_min": -1.0,
    "pan_max": 1.0,
    "tilt_min": -1.0,
    "tilt_max": 1.0,
  },
  "settle_angular_threshold_deg": 0.05,
  "settle_interval_s": 0.5,
  "composition_order": ["pan", "home", "tilt"],
  "axes": {
    "pan": {
      "axis": [0.0, 0.0, 1.0],
      "frame": "world_home",
      "curve": [0.0, 180.0],
      "home_position": 0.0,
      "approach_direction": "increasing",
      "backlash": 0.1,
      "backlash_home_tolerance_deg": 0.2,
      "backlash_history_s": 10.0,
    },
    "tilt": {
      "axis": [1.0, 0.0, 0.0],
      "frame": "camera_local",
      "curve": [0.0, -45.0],
      "home_position": 0.0,
      "approach_direction": "decreasing",
      "backlash": [[-1.0, 0.1], [1.0, 0.15]],
      "backlash_home_tolerance_deg": 0.2,
      "backlash_history_s": 10.0,
    },
  },
  "quality": {"reprojection_rms_px": 1.2},
  "provenance": {"camera_model": "test-camera"},
}

_DELETE = object()


def _mutated(path, value=_DELETE):
  calibration = deepcopy(PTZ_CALIBRATION)
  target = calibration
  for key in path[:-1]:
    target = target[key]
  if value is _DELETE:
    del target[path[-1]]
  else:
    target[path[-1]] = value
  return calibration


# name -> (calibration, expected stable error)
MALFORMED_CALIBRATIONS = {
  "not_object": ([], "ptz_calibration: not_object"),
  "partial": ({"calibration_version": "partial"}, "parameterization_version: required"),
  "missing_position_space_uri": (
    _mutated(["position_space", "uri"]), "position_space.uri: required"),
  "empty_calibration_version": (
    _mutated(["calibration_version"], ""), "calibration_version: invalid_length"),
  "numeric_calibration_version": (
    _mutated(["calibration_version"], 5), "calibration_version: not_string"),
  "duplicate_composition_element": (
    _mutated(["composition_order"], ["pan", "pan", "home"]),
    "composition_order: invalid_composition_order"),
  "composition_missing_tilt": (
    _mutated(["composition_order"], ["pan", "home"]),
    "composition_order: invalid_composition_order"),
  "composition_not_array": (
    _mutated(["composition_order"], "pan,home,tilt"),
    "composition_order: invalid_composition_order"),
  "frame_inconsistent_with_order": (
    _mutated(["axes", "tilt", "frame"], "world_home"), "axes.tilt.frame: frame_order_mismatch"),
  "order_inconsistent_with_frames": (
    _mutated(["composition_order"], ["tilt", "home", "pan"]),
    "axes.pan.frame: frame_order_mismatch"),
  "unknown_frame": (_mutated(["axes", "pan", "frame"], "world"), "axes.pan.frame: invalid_choice"),
  "axis_not_unit": (
    _mutated(["axes", "pan", "axis"], [0.5, 0.5, 0.5]), "axes.pan.axis: not_unit_vector"),
  "axis_wrong_length": (_mutated(["axes", "pan", "axis"], [0.0, 1.0]), "axes.pan.axis: invalid_size"),
  "constant_curve": (
    _mutated(["axes", "pan", "curve"], [1.0, 0.0, 0.0]), "axes.pan.curve: constant_curve"),
  "curve_too_short": (_mutated(["axes", "pan", "curve"], [1.0]), "axes.pan.curve: invalid_size"),
  "home_outside_range": (
    _mutated(["axes", "tilt", "home_position"], 1.5), "axes.tilt.home_position: out_of_range"),
  "invalid_approach_direction": (
    _mutated(["axes", "tilt", "approach_direction"], "up"),
    "axes.tilt.approach_direction: invalid_choice"),
  "backlash_node_not_pair": (
    _mutated(["axes", "pan", "backlash"], [[0.1, 0.2, 0.3]]), "axes.pan.backlash[0]: invalid_node"),
  "backlash_no_nodes": (_mutated(["axes", "pan", "backlash"], []), "axes.pan.backlash: invalid_size"),
  "backlash_too_many_nodes": (
    _mutated(["axes", "pan", "backlash"], [[index / 100, 0.1] for index in range(65)]),
    "axes.pan.backlash: invalid_size"),
  "duplicate_backlash_positions": (
    _mutated(["axes", "pan", "backlash"], [[0.1, 1.0], [0.1, 2.0]]),
    "axes.pan.backlash[1]: duplicate_position"),
  "negative_backlash": (_mutated(["axes", "tilt", "backlash"], -0.1), "axes.tilt.backlash: negative"),
  "negative_backlash_node": (
    _mutated(["axes", "tilt", "backlash"], [[-1.0, -0.1]]), "axes.tilt.backlash[0]: negative"),
  "unknown_top_level_field": (_mutated(["invert"], True), "invert: unknown_field"),
  "unknown_axis_field": (_mutated(["axes", "pan", "scale"], 153.36), "axes.pan.scale: unknown_field"),
  "unknown_quality_field": (_mutated(["quality", "extra"], 1.0), "quality.extra: unknown_field"),
  "bool_as_number": (_mutated(["settle_interval_s"], True), "settle_interval_s: not_number"),
  "bool_home_position": (
    _mutated(["axes", "pan", "home_position"], False), "axes.pan.home_position: not_number"),
  "string_as_number": (_mutated(["settle_interval_s"], "0.5"), "settle_interval_s: not_number"),
  "provenance_not_object": (_mutated(["provenance"], "lab"), "provenance: not_object"),
  "zero_settle_threshold": (
    _mutated(["settle_angular_threshold_deg"], 0), "settle_angular_threshold_deg: not_positive"),
  "zero_settle_interval": (_mutated(["settle_interval_s"], 0.0), "settle_interval_s: not_positive"),
  "zero_backlash_home_tolerance": (
    _mutated(["axes", "pan", "backlash_home_tolerance_deg"], 0),
    "axes.pan.backlash_home_tolerance_deg: not_positive"),
  "zero_backlash_history": (
    _mutated(["axes", "tilt", "backlash_history_s"], 0),
    "axes.tilt.backlash_history_s: not_positive"),
  "settle_threshold_exceeds_tilt_travel": (
    _mutated(["settle_angular_threshold_deg"], 100.0),
    "settle_angular_threshold_deg: exceeds_travel"),
  "home_tolerance_exceeds_travel": (
    _mutated(["axes", "tilt", "backlash_home_tolerance_deg"], 100.0),
    "axes.tilt.backlash_home_tolerance_deg: exceeds_travel"),
  "negative_residual": (
    _mutated(["quality", "reprojection_rms_px"], -0.1), "quality.reprojection_rms_px: negative"),
}

INCOMPATIBLE_CALIBRATIONS = {
  "unsupported_parameterization": (
    _mutated(["parameterization_version"], "v2"), "parameterization_version: unsupported_version"),
  "empty_pan_range": (_mutated(["position_space", "pan_min"], 1.0), "position_space.pan_min: invalid_range"),
  "inverted_tilt_range": (
    _mutated(["position_space", "tilt_min"], 2.0), "position_space.tilt_min: invalid_range"),
}

INVALID_CALIBRATIONS = {**MALFORMED_CALIBRATIONS, **INCOMPATIBLE_CALIBRATIONS}


@override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.5")
class PTZCalibrationValidatorTest(TestCase):

  def test_explicit_camera_id_must_be_topic_safe(self):
    for camera_id in ("North/West", "camera+one", "camera#one", "camera\x00one"):
      serializer = CamSerializer(data={"name": "Camera", "sensor_id": camera_id})
      self.assertFalse(serializer.is_valid())
      self.assertIn("sensor_id", serializer.errors)

  def test_derived_camera_id_must_be_topic_safe(self):
    serializer = CamSerializer(data={"name": "North/West"})
    self.assertFalse(serializer.is_valid())
    self.assertIn("name", serializer.errors)

  def test_valid_calibration_is_accepted(self):
    self.assertEqual(validate_ptz_calibration(PTZ_CALIBRATION, "1.5"), PTZ_CALIBRATION)
    serializer = CamSerializer()
    self.assertEqual(serializer.validate_ptz_calibration(PTZ_CALIBRATION), PTZ_CALIBRATION)

  def test_provenance_is_optional(self):
    calibration = _mutated(["provenance"])
    self.assertEqual(validate_ptz_calibration(calibration, "1.5"), calibration)

  def test_invalid_calibration_reports_stable_path_and_code(self):
    for name, (calibration, expected) in INVALID_CALIBRATIONS.items():
      with self.subTest(name=name):
        with self.assertRaises(PTZCalibrationError) as raised:
          validate_ptz_calibration(calibration, "1.5")
        self.assertEqual(str(raised.exception), expected)

  def test_non_finite_values_are_rejected(self):
    for value in (float("inf"), float("-inf"), float("nan")):
      with self.subTest(value=value):
        with self.assertRaises(PTZCalibrationError) as raised:
          validate_ptz_calibration(_mutated(["axes", "pan", "axis"], [value, 0.0, 0.0]), "1.5")
        self.assertEqual(str(raised.exception), "axes.pan.axis: not_finite")

  def test_axis_travel_uses_curve_extrema(self):
    self.assertAlmostEqual(axis_travel_deg([0.0, 180.0], (-1.0, 1.0)), 360.0)
    self.assertAlmostEqual(axis_travel_deg([0.0, 0.0, 10.0], (-1.0, 1.0)), 10.0)
    self.assertAlmostEqual(axis_travel_deg([0.0, -30.0, 0.0, 40.0], (-0.75, 0.75)), 20.0)

  def test_residual_above_import_threshold_is_rejected(self):
    with self.assertRaises(PTZCalibrationError) as raised:
      validate_ptz_calibration(PTZ_CALIBRATION, "1.0")
    self.assertEqual(str(raised.exception), "quality.reprojection_rms_px: exceeds_threshold")

  def test_missing_or_invalid_import_threshold_rejects_calibration(self):
    for threshold in (None, "", "invalid", "nan", "inf", "0", "-1"):
      with self.subTest(threshold=threshold):
        with self.assertRaises(PTZCalibrationError) as raised:
          validate_ptz_calibration(PTZ_CALIBRATION, threshold)
        self.assertEqual(
          str(raised.exception), "quality.reprojection_rms_px: threshold_not_configured")

  def test_serializer_reports_stable_error(self):
    serializer = CamSerializer(data={
      "name": "Bad PTZ", "ptz_calibration": _mutated(["axes", "pan", "axis"], [0.5, 0.5, 0.5])})
    self.assertFalse(serializer.is_valid())
    self.assertEqual(serializer.errors["ptz_calibration"], ["axes.pan.axis: not_unit_vector"])
    self.assertEqual(serializer.errors["ptz_calibration"][0].code, "not_unit_vector")

  def test_serializer_does_not_expose_exception_message(self):
    error = PTZCalibrationError("axes.pan.axis", "not_unit_vector")
    error.args = ("Traceback: internal server details must not reach the API",)
    serializer = CamSerializer(data={"name": "Bad PTZ", "ptz_calibration": PTZ_CALIBRATION})
    with patch("manager.serializers.validate_ptz_calibration", side_effect=error):
      self.assertFalse(serializer.is_valid())
    self.assertEqual(serializer.errors["ptz_calibration"], ["axes.pan.axis: not_unit_vector"])
    self.assertEqual(serializer.errors["ptz_calibration"][0].code, "not_unit_vector")


class PTZCalibrationInvalidationTest(TestCase):

  def test_incompatible_existing_camera_id_does_not_abort_other_notifications(self):
    client = Mock()
    client.publish.return_value.is_published.return_value = True

    class FakePubSub:
      CMD_CAMERA_CONFIG = PubSub.CMD_CAMERA_CONFIG
      CMD_DATABASE = PubSub.CMD_DATABASE
      CMD_KUBECLIENT = PubSub.CMD_KUBECLIENT
      formatTopic = staticmethod(PubSub.formatTopic)

      def __new__(cls, *args, **kwargs):
        return client

    with patch.dict("os.environ", {"BROKER": "broker"}), \
         patch("manager.models.PubSub", FakePubSub):
      sendUpdateCommand(
        camera_data={"sensor_id": "North/West"},
        camera_config_update={
          "camera_id": "North/West",
          "calibration_version": "legacy-v1",
        },
      )

    published_topics = [call.args[0] for call in client.publish.call_args_list]
    self.assertEqual(published_topics, [
      PubSub.formatTopic(PubSub.CMD_KUBECLIENT),
      PubSub.formatTopic(PubSub.CMD_DATABASE),
    ])

  def test_camera_save_commit_publishes_calibration_version(self):
    with patch("manager.models.sendUpdateCommand") as send_update:
      with self.captureOnCommitCallbacks(execute=True):
        Cam.objects.create(
          sensor_id="ptz-camera-commit",
          name="PTZ camera commit",
          type="camera",
          ptz_calibration=PTZ_CALIBRATION,
        )
      self.assertTrue(any(
        call.kwargs.get("camera_config_update") == {
          "camera_id": "ptz-camera-commit",
          "calibration_version": "cam1-v1",
        }
        for call in send_update.call_args_list
      ))

  def test_camera_save_rollback_does_not_publish_invalidation(self):
    with patch("manager.models.sendUpdateCommand") as send_update:
      with self.captureOnCommitCallbacks(execute=True):
        try:
          with transaction.atomic():
            Cam.objects.create(
              sensor_id="ptz-camera",
              name="PTZ camera",
              type="camera",
              ptz_calibration=PTZ_CALIBRATION,
            )
            raise RuntimeError("rollback")
        except RuntimeError:
          pass
      send_update.assert_not_called()


class PTZCalibrationAPITest(TestCase):

  @override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.5")
  def test_camera_api_round_trip_and_read_only_client(self):
    admin = User.objects.create_superuser("ptz-admin", "ptz-admin@example.com", "unused")
    reader = User.objects.create_user("ptz-reader", "ptz-reader@example.com", "unused")
    admin_token = Token.objects.create(user=admin)
    reader_token = Token.objects.create(user=reader)
    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    created = admin_client.post(
      "/api/v1/camera",
      {"name": "PTZ API Camera", "ptz_calibration": PTZ_CALIBRATION},
      format="json",
    )
    self.assertEqual(created.status_code, 201, created.data)
    camera_uid = created.data["uid"]
    self.assertEqual(created.data["ptz_calibration"], PTZ_CALIBRATION)

    updated_calibration = deepcopy(PTZ_CALIBRATION)
    updated_calibration["calibration_version"] = "cam1-v2"
    updated = admin_client.put(
      f"/api/v1/camera/{camera_uid}",
      {"name": "PTZ API Camera", "ptz_calibration": updated_calibration},
      format="json",
    )
    self.assertEqual(updated.status_code, 200, updated.data)
    self.assertEqual(updated.data["ptz_calibration"]["calibration_version"], "cam1-v2")

    reader_client = APIClient()
    reader_client.credentials(HTTP_AUTHORIZATION=f"Token {reader_token.key}")
    detail = reader_client.get(f"/api/v1/camera/{camera_uid}")
    self.assertEqual(detail.status_code, 200)
    self.assertEqual(detail.data["ptz_calibration"], updated_calibration)
    collection = reader_client.get("/api/v1/cameras")
    self.assertEqual(collection.status_code, 200)
    self.assertEqual(collection.data["results"][0]["ptz_calibration"], updated_calibration)

INTRINSICS = {"fx": 1000.0, "fy": 1000.0, "cx": 960.0, "cy": 540.0}
EULER_HOME = {"translation": [2.0, 3.0, 4.0], "rotation": [-150.0, 5.0, 10.0], "scale": [1.0, 1.0, 1.0]}


def _ground_correspondences(pose_matrix):
  """Project chosen pixels onto the z=0 ground plane from a camera-to-scene pose."""
  pose = np.array(pose_matrix)
  inverse_k = np.linalg.inv(np.array([
    [INTRINSICS["fx"], 0.0, INTRINSICS["cx"]],
    [0.0, INTRINSICS["fy"], INTRINSICS["cy"]],
    [0.0, 0.0, 1.0],
  ]))
  pixels = [(560.0, 340.0), (1360.0, 340.0), (960.0, 540.0),
            (560.0, 740.0), (1360.0, 740.0), (800.0, 900.0)]
  map_points = []
  for pixel in pixels:
    ray = pose[:3, :3] @ (inverse_k @ np.array([pixel[0], pixel[1], 1.0]))
    distance = -pose[2, 3] / ray[2]
    assert distance > 0
    map_points.append((pose[:3, 3] + distance * ray).tolist())
  return [value for pixel in pixels for value in pixel] \
    + [value for point in map_points for value in point]


@override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.5")
class PTZCalibrationTransformAPITest(TestCase):

  def setUp(self):
    admin = User.objects.create_superuser("ptz-admin", "ptz-admin@example.com", "unused")
    reader = User.objects.create_user("positioning", "positioning@example.com", "unused")
    self.admin = APIClient()
    self.admin.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
    self.reader = APIClient()
    self.reader.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=reader).key}")
    self.scene = Scene.objects.create(name=f"ptz-scene-{self._testMethodName}")

  def _create(self, payload):
    response = self.admin.post("/api/v1/camera", {
      "scene": str(self.scene.pk), "intrinsics": INTRINSICS, "resolution": [1920, 1080],
      "ptz_calibration": PTZ_CALIBRATION, **payload,
    }, format="json")
    self.assertEqual(response.status_code, 201, response.data)
    return response.data["uid"]

  def _assert_complete_home(self, uid, transform_type):
    response = self.reader.get(f"/api/v1/camera/{uid}")
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data["transform_type"], transform_type)
    self.assertEqual(data["ptz_calibration"], PTZ_CALIBRATION)
    for field in ("translation", "rotation", "scale", "transforms", "intrinsics", "pose_matrix"):
      self.assertIn(field, data)
    pose = np.array(data["pose_matrix"])
    self.assertEqual(pose.shape, (4, 4))
    np.testing.assert_allclose(pose[3], [0.0, 0.0, 0.0, 1.0])
    np.testing.assert_allclose(pose[:3, 3], data["translation"], atol=1e-6)
    return data

  def test_euler_and_point_correspondence_cameras_expose_complete_home_pose(self):
    euler_uid = self._create({"name": "PTZ Euler", "transform_type": "euler", **EULER_HOME})
    euler = self._assert_complete_home(euler_uid, "euler")
    np.testing.assert_allclose(euler["translation"], EULER_HOME["translation"], atol=1e-6)
    np.testing.assert_allclose(euler["rotation"], EULER_HOME["rotation"], atol=1e-6)

    correspondences = _ground_correspondences(euler["pose_matrix"])
    point_uid = self._create({
      "name": "PTZ Points", "transform_type": "3d-2d point correspondence",
      "transforms": correspondences,
    })
    point = self._assert_complete_home(point_uid, "3d-2d point correspondence")
    np.testing.assert_allclose(point["transforms"], correspondences, atol=1e-6)
    np.testing.assert_allclose(point["pose_matrix"], euler["pose_matrix"], atol=1e-3)

    cameras = self.reader.get("/api/v1/cameras").json()["results"]
    by_uid = {camera["uid"]: camera for camera in cameras}
    self.assertEqual(by_uid[euler_uid]["pose_matrix"], euler["pose_matrix"])
    self.assertEqual(by_uid[point_uid]["ptz_calibration"], PTZ_CALIBRATION)

  def test_read_only_client_cannot_write_camera(self):
    uid = self._create({"name": "PTZ Locked", "transform_type": "euler", **EULER_HOME})
    changed = _mutated(["calibration_version"], "reader-write")

    updated = self.reader.put(
      f"/api/v1/camera/{uid}", {"name": "PTZ Locked", "ptz_calibration": changed}, format="json")
    self.assertEqual(updated.status_code, 403)
    created = self.reader.post(
      "/api/v1/camera", {"name": "PTZ Reader", "ptz_calibration": changed}, format="json")
    self.assertEqual(created.status_code, 403)
    self.assertEqual(Cam.objects.get(sensor_id=uid).ptz_calibration, PTZ_CALIBRATION)
    self.assertFalse(Cam.objects.filter(name="PTZ Reader").exists())

  def test_invalid_calibration_returns_stable_400_body(self):
    uid = self._create({"name": "PTZ Target", "transform_type": "euler", **EULER_HOME})
    for name, (calibration, expected) in INVALID_CALIBRATIONS.items():
      with self.subTest(name=name):
        updated = self.admin.put(
          f"/api/v1/camera/{uid}",
          {"name": "PTZ Target", "ptz_calibration": calibration}, format="json")
        self.assertEqual(updated.status_code, 400)
        self.assertEqual(updated.json(), {"ptz_calibration": [expected]})

        created = self.admin.post(
          "/api/v1/camera", {"name": "PTZ Rejected", "ptz_calibration": calibration},
          format="json")
        self.assertEqual(created.status_code, 400)
        self.assertEqual(created.json(), {"ptz_calibration": [expected]})
    self.assertEqual(Cam.objects.get(sensor_id=uid).ptz_calibration, PTZ_CALIBRATION)
    self.assertFalse(Cam.objects.filter(name="PTZ Rejected").exists())

  def test_non_finite_json_is_rejected(self):
    uid = self._create({"name": "PTZ Finite", "transform_type": "euler", **EULER_HOME})
    body = json.dumps({"name": "PTZ Finite", "ptz_calibration": _mutated(
      ["axes", "pan", "axis"], [float("inf"), 0.0, 0.0])})
    response = self.admin.put(f"/api/v1/camera/{uid}", body, content_type="application/json")
    self.assertEqual(response.status_code, 400)
    self.assertEqual(Cam.objects.get(sensor_id=uid).ptz_calibration, PTZ_CALIBRATION)

  @override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.0")
  def test_residual_above_threshold_returns_stable_400_body(self):
    response = self.admin.post(
      "/api/v1/camera", {"name": "PTZ Residual", "ptz_calibration": PTZ_CALIBRATION},
      format="json")
    self.assertEqual(response.status_code, 400)
    self.assertEqual(
      response.json(), {"ptz_calibration": ["quality.reprojection_rms_px: exceeds_threshold"]})


def _acl_check(client, username, topic, acc):
  return client.post("/api/v1/aclcheck", {"username": username, "topic": topic, "acc": acc},
                     format="json")


def _pose_topic(source_id):
  return PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=source_id)


class PoseACLTest(TestCase):

  def setUp(self):
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    self.client = APIClient()
    self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
    self.scene_a = Scene.objects.create(name=f"acl-a-{self._testMethodName}")
    self.scene_b = Scene.objects.create(name=f"acl-b-{self._testMethodName}")
    Cam.objects.create(sensor_id="ptz-a", name="PTZ A", type="camera", scene=self.scene_a)
    Cam.objects.create(sensor_id="ptz-b", name="PTZ B", type="camera", scene=self.scene_b)
    Cam.objects.create(sensor_id="ptz-none", name="PTZ None", type="camera")

  def _check(self, username, source_id, acc):
    return _acl_check(self.client, username, _pose_topic(source_id), acc)

  def test_pose_read_is_limited_to_assigned_scenes(self):
    consumer_a = User.objects.create_user("consumer-a", "consumer-a@example.com", "unused")
    consumer_b = User.objects.create_user("consumer-b", "consumer-b@example.com", "unused")
    PubSubACL.objects.create(user=consumer_a, topic="POSITIONING_POSE", access=1).scenes.set([self.scene_a])
    PubSubACL.objects.create(user=consumer_b, topic="POSITIONING_POSE", access=1).scenes.set([self.scene_b])

    for acc in (1, 4):
      self.assertEqual(self._check("consumer-a", "ptz-a", acc).status_code, 200)
      self.assertEqual(self._check("consumer-b", "ptz-b", acc).status_code, 200)
      cross = self._check("consumer-a", "ptz-b", acc)
      self.assertEqual(cross.status_code, 403)
      self.assertEqual(cross.data["result"], "deny")
      self.assertEqual(self._check("consumer-b", "ptz-a", acc).status_code, 403)
    self.assertEqual(self._check("consumer-a", "ptz-none", 4).status_code, 403)
    self.assertEqual(self._check("consumer-a", "+", 4).status_code, 403)

  def test_pose_read_scope_follows_camera_scene_membership(self):
    consumer = User.objects.create_user("consumer-a", "consumer-a@example.com", "unused")
    PubSubACL.objects.create(user=consumer, topic="POSITIONING_POSE", access=1).scenes.set([self.scene_a])
    self.assertEqual(self._check("consumer-a", "ptz-b", 4).status_code, 403)

    camera = Cam.objects.get(sensor_id="ptz-b")
    camera.scene = self.scene_a
    camera.save()
    self.assertEqual(self._check("consumer-a", "ptz-b", 4).status_code, 200)

    camera.scene = None
    camera.save()
    self.assertEqual(self._check("consumer-a", "ptz-b", 4).status_code, 403)

  def test_pose_read_without_scene_scope_is_denied(self):
    consumer = User.objects.create_user("unscoped", "unscoped@example.com", "unused")
    PubSubACL.objects.create(user=consumer, topic="POSITIONING_POSE", access=1)
    self.assertEqual(self._check("unscoped", "ptz-a", 1).status_code, 403)
    self.assertEqual(self._check("unscoped", "ptz-a", 4).status_code, 403)

  def test_superuser_needs_explicit_positioning_acl(self):
    User.objects.create_superuser("other-admin", "other-admin@example.com", "unused")
    self.assertEqual(self._check("other-admin", "ptz-a", 4).status_code, 403)
    self.assertEqual(self._check("other-admin", "ptz-a", 2).status_code, 403)
    status_topic = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id="positioning-default")
    self.assertEqual(_acl_check(self.client, "other-admin", status_topic, 4).status_code, 403)
    camera_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id="ptz-a")
    self.assertEqual(_acl_check(self.client, "other-admin", camera_topic, 2).status_code, 200)

  def test_pose_write_is_limited_to_topic_publisher(self):
    publisher = User.objects.create_user("pose-publisher", "pose-publisher@example.com", "unused")
    PubSubACL.objects.create(user=publisher, topic="POSITIONING_POSE", access=2)
    consumer = User.objects.create_user("consumer-a", "consumer-a@example.com", "unused")
    PubSubACL.objects.create(user=consumer, topic="POSITIONING_POSE", access=1).scenes.set([self.scene_a])

    allowed = self._check("pose-publisher", "ptz-b", 2)
    self.assertEqual(allowed.status_code, 200)
    self.assertEqual(allowed.data["result"], "allow")
    self.assertEqual(self._check("pose-publisher", "ptz-b", 4).status_code, 403)
    self.assertEqual(self._check("consumer-a", "ptz-a", 2).status_code, 403)

  def test_positioning_identity_pose_write_is_denied(self):
    resolver = User.objects.create_user("positioning", "positioning@example.com", "unused")
    PubSubACL.objects.create(user=resolver, topic="POSITIONING_POSE", access=2)
    denied = self._check("positioning", "ptz-a", 2)
    self.assertEqual(denied.status_code, 403)
    self.assertEqual(denied.data["result"], "deny")


class ProvisionedPositioningACLTest(TestCase):

  def _provision(self, auth_name, username):
    workdir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, workdir)
    shutil.copy(USER_ACCESS_CONFIG, workdir)
    auth_path = os.path.join(workdir, auth_name)
    with open(auth_path, "w") as auth_file:
      json.dump({"user": username, "password": "unused-password"}, auth_file)
    previous = os.getcwd()
    os.chdir(workdir)
    try:
      call_command("createuser", auth_path)
    finally:
      os.chdir(previous)

  def test_provisioned_acls_have_no_static_source_lists(self):
    config = json.loads(USER_ACCESS_CONFIG.read_text())
    for identity in config.values():
      for acl in identity["acls"]:
        self.assertNotIn("sources", acl)
    positioning_topics = {acl["topic"] for acl in config["positioning.auth"]["acls"]}
    self.assertNotIn("POSITIONING_POSE", positioning_topics)

  def test_controller_identity_reads_only_scene_assigned_cameras(self):
    self._provision("controller.auth", "scenectrl")
    self._provision("browser.auth", "webuser")
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
    scene = Scene.objects.create(name="provisioned-scene")
    Cam.objects.create(sensor_id="ptz-in", name="PTZ In", type="camera", scene=scene)
    Cam.objects.create(sensor_id="ptz-out", name="PTZ Out", type="camera")
    controller = User.objects.get(username="scenectrl")
    self.assertTrue(controller.is_superuser)
    pose_acl = PubSubACL.objects.get(user=controller, topic="POSITIONING_POSE")
    self.assertTrue(pose_acl.all_scenes)

    self.assertEqual(_acl_check(client, "scenectrl", _pose_topic("ptz-in"), 4).status_code, 200)
    denied = _acl_check(client, "scenectrl", _pose_topic("ptz-out"), 4)
    self.assertEqual(denied.status_code, 403)
    self.assertEqual(denied.data["result"], "deny")
    self.assertEqual(_acl_check(client, "scenectrl", _pose_topic("missing"), 4).status_code, 403)
    self.assertEqual(_acl_check(client, "scenectrl", _pose_topic("+"), 4).status_code, 403)
    self.assertEqual(_acl_check(client, "scenectrl", _pose_topic("ptz-in"), 2).status_code, 403)
    status_topic = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id="positioning-default")
    self.assertEqual(_acl_check(client, "scenectrl", status_topic, 4).status_code, 200)
    self.assertEqual(_acl_check(client, "scenectrl", status_topic, 2).status_code, 403)

    self.assertEqual(_acl_check(client, "webuser", _pose_topic("ptz-in"), 4).status_code, 403)
