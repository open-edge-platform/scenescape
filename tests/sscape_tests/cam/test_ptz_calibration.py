# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from manager.models import Cam, PubSubACL, Scene
from manager.serializers import CamSerializer
from scene_common.mqtt import PubSub


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


class PTZCalibrationSerializerTest(TestCase):

  @override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.5")
  def test_valid_calibration_is_accepted(self):
    serializer = CamSerializer()
    self.assertEqual(serializer.validate_ptz_calibration(PTZ_CALIBRATION), PTZ_CALIBRATION)

  @override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.5")
  def test_partial_calibration_is_rejected_with_field_detail(self):
    serializer = CamSerializer()
    with self.assertRaises(ValidationError) as raised:
      serializer.validate_ptz_calibration({"calibration_version": "partial"})
    self.assertIn("position_space", str(raised.exception))

  @override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.5")
  def test_non_finite_axis_value_is_rejected(self):
    serializer = CamSerializer()
    calibration = deepcopy(PTZ_CALIBRATION)
    calibration["axes"]["pan"]["axis"][0] = float("inf")
    with self.assertRaises(ValidationError):
      serializer.validate_ptz_calibration(calibration)

  @override_settings(PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX="1.0")
  def test_residual_above_import_threshold_is_rejected(self):
    serializer = CamSerializer()
    with self.assertRaises(ValidationError) as raised:
      serializer.validate_ptz_calibration(PTZ_CALIBRATION)
    self.assertIn("import threshold", str(raised.exception))

  def test_missing_import_threshold_rejects_calibration(self):
    serializer = CamSerializer()
    with self.assertRaises(ValidationError) as raised:
      serializer.validate_ptz_calibration(PTZ_CALIBRATION)
    self.assertIn("not configured", str(raised.exception))


class PTZCalibrationInvalidationTest(TestCase):

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

  def test_pose_acl_requires_camera_scene_assignment(self):
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    consumer = User.objects.create_user("ptz-consumer", "ptz-consumer@example.com", "unused")
    admin_token = Token.objects.create(user=admin)
    PubSubACL.objects.create(user=consumer, topic="POSITIONING_POSE", access=1)
    scene = Scene.objects.create(name="assigned-scene", map="scene-map")
    Cam.objects.create(sensor_id="assigned-ptz", name="Assigned PTZ", type="camera", scene=scene)
    Cam.objects.create(sensor_id="unassigned-ptz", name="Unassigned PTZ", type="camera")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    assigned = client.post("/api/v1/aclcheck", {
      "username": consumer.username,
      "topic": PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id="assigned-ptz"),
      "acc": 1,
    }, format="json")
    self.assertEqual(assigned.status_code, 200)
    self.assertEqual(assigned.data["result"], "allow")

    unassigned = client.post("/api/v1/aclcheck", {
      "username": consumer.username,
      "topic": PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id="unassigned-ptz"),
      "acc": 1,
    }, format="json")
    self.assertEqual(unassigned.status_code, 403)
    self.assertEqual(unassigned.data["result"], "deny")