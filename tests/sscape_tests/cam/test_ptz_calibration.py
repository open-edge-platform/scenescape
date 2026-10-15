# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from manager.models import Cam, PubSubACL, Scene, sendUpdateCommand
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

  def test_explicit_camera_id_must_be_topic_safe(self):
    for camera_id in ("North/West", "camera+one", "camera#one", "camera\x00one"):
      serializer = CamSerializer(data={"name": "Camera", "sensor_id": camera_id})
      self.assertFalse(serializer.is_valid())
      self.assertIn("sensor_id", serializer.errors)

  def test_derived_camera_id_must_be_topic_safe(self):
    serializer = CamSerializer(data={"name": "North/West"})
    self.assertFalse(serializer.is_valid())
    self.assertIn("name", serializer.errors)

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

  def test_invalid_import_threshold_rejects_calibration(self):
    serializer = CamSerializer()
    for threshold in ("", "invalid", "nan", "inf", "0", "-1"):
      with self.subTest(threshold=threshold), self.settings(
        PTZ_CALIBRATION_RESIDUAL_THRESHOLD_PX=threshold
      ):
        with self.assertRaises(ValidationError):
          serializer.validate_ptz_calibration(PTZ_CALIBRATION)


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

  def _acl_check(self, client, username, source_id, acc):
    return client.post("/api/v1/aclcheck", {
      "username": username,
      "topic": PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=source_id),
      "acc": acc,
    }, format="json")

  def test_pose_acl_is_limited_to_user_assigned_scene(self):
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    consumer_a = User.objects.create_user("consumer-a", "consumer-a@example.com", "unused")
    consumer_b = User.objects.create_user("consumer-b", "consumer-b@example.com", "unused")
    admin_token = Token.objects.create(user=admin)
    scene_a = Scene.objects.create(name="scene-a", map="scene-a-map")
    scene_b = Scene.objects.create(name="scene-b", map="scene-b-map")
    Cam.objects.create(sensor_id="ptz-a", name="PTZ A", type="camera", scene=scene_a)
    Cam.objects.create(sensor_id="ptz-b", name="PTZ B", type="camera", scene=scene_b)
    PubSubACL.objects.create(user=consumer_a, topic="POSITIONING_POSE", access=1).scenes.set([scene_a])
    PubSubACL.objects.create(user=consumer_b, topic="POSITIONING_POSE", access=1).scenes.set([scene_b])
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    self.assertEqual(self._acl_check(client, "consumer-a", "ptz-a", 1).status_code, 200)
    self.assertEqual(self._acl_check(client, "consumer-b", "ptz-b", 1).status_code, 200)

    cross_a = self._acl_check(client, "consumer-a", "ptz-b", 1)
    self.assertEqual(cross_a.status_code, 403)
    self.assertEqual(cross_a.data["result"], "deny")
    cross_b = self._acl_check(client, "consumer-b", "ptz-a", 1)
    self.assertEqual(cross_b.status_code, 403)
    self.assertEqual(cross_b.data["result"], "deny")

  def test_pose_acl_without_scene_assignment_denies(self):
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    consumer = User.objects.create_user("unscoped", "unscoped@example.com", "unused")
    admin_token = Token.objects.create(user=admin)
    scene = Scene.objects.create(name="scene-x", map="scene-x-map")
    Cam.objects.create(sensor_id="ptz-x", name="PTZ X", type="camera", scene=scene)
    PubSubACL.objects.create(user=consumer, topic="POSITIONING_POSE", access=3)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    self.assertEqual(self._acl_check(client, "unscoped", "ptz-x", 1).status_code, 403)
    self.assertEqual(self._acl_check(client, "unscoped", "ptz-x", 2).status_code, 403)

  def test_positioning_publishes_only_assigned_sources(self):
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    publisher = User.objects.create_user("pose-publisher", "pose-publisher@example.com", "unused")
    admin_token = Token.objects.create(user=admin)
    scene_a = Scene.objects.create(name="scene-a", map="scene-a-map")
    scene_b = Scene.objects.create(name="scene-b", map="scene-b-map")
    Cam.objects.create(sensor_id="ptz-a", name="PTZ A", type="camera", scene=scene_a)
    Cam.objects.create(sensor_id="ptz-b", name="PTZ B", type="camera", scene=scene_b)
    PubSubACL.objects.create(
      user=publisher, topic="POSITIONING_POSE", access=2, sources=["ptz-a", "missing-ptz"])
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    allowed = self._acl_check(client, "pose-publisher", "ptz-a", 2)
    self.assertEqual(allowed.status_code, 200)
    self.assertEqual(allowed.data["result"], "allow")
    self.assertEqual(self._acl_check(client, "pose-publisher", "ptz-b", 2).status_code, 403)
    self.assertEqual(self._acl_check(client, "pose-publisher", "missing-ptz", 2).status_code, 403)
    self.assertEqual(self._acl_check(client, "pose-publisher", "ptz-a", 1).status_code, 403)

  def test_positioning_identity_pose_write_is_denied(self):
    admin = User.objects.create_superuser("acl-admin", "acl-admin@example.com", "unused")
    resolver = User.objects.create_user("positioning", "positioning@example.com", "unused")
    admin_token = Token.objects.create(user=admin)
    scene = Scene.objects.create(name="scene-a", map="scene-a-map")
    Cam.objects.create(sensor_id="ptz-a", name="PTZ A", type="camera", scene=scene)
    PubSubACL.objects.create(user=resolver, topic="POSITIONING_POSE", access=2, sources=["ptz-a"])
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {admin_token.key}")

    denied = self._acl_check(client, "positioning", "ptz-a", 2)
    self.assertEqual(denied.status_code, 403)
    self.assertEqual(denied.data["result"], "deny")

  def test_provisioned_positioning_identity_has_unassigned_pose_acl(self):
    config_path = Path(__file__).resolve().parents[3] / "manager" / "config" / "user_access_config.json"
    acls = json.loads(config_path.read_text())["positioning.auth"]["acls"]
    pose = [acl for acl in acls if acl["topic"] == "POSITIONING_POSE"]
    self.assertEqual(pose, [{"topic": "POSITIONING_POSE", "access": 2, "sources": []}])
