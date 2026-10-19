# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""In-process PTZ Resolver acceptance and fail-closed behavior."""

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from scipy.spatial.transform import Rotation

from positioning.ptz_model import load_ptz_model
from positioning.manager_calibration import ManagerCalibrationError, ManagerCalibrationLoader
from positioning.resolver import PTZResolver, PTZSourceCalibration
from positioning.v1 import ptz_pb2
from positioning.pose_math import apply_backlash, axis_angle_degrees, compose_ptz_rotation

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads(
  (REPO_ROOT / "tests" / "data" / "ptz" / "provisional_pose_math.json").read_text())
MODEL = load_ptz_model(FIXTURE["ptz_calibration"])
HOME_MATRIX = np.eye(4)
HOME_MATRIX[:3, :3] = Rotation.from_euler(
  "XYZ", FIXTURE["home_pose"]["rotation_euler_xyz_deg"], degrees=True).as_matrix()
HOME_MATRIX[:3, 3] = FIXTURE["home_pose"]["translation_m"]
CALIBRATION = PTZSourceCalibration(MODEL, HOME_MATRIX, "scene:scene-a")
SOURCE_ID = "atag-ptzcam3"
START_NS = 1_790_000_000_000_000_000
RING_SIZE = 52


class FakeClock:
  def __init__(self, timestamp_ns=START_NS):
    self.timestamp_ns = timestamp_ns

  def __call__(self):
    return self.timestamp_ns


def make_resolver(clock, published, calibrations=None, ring_size=RING_SIZE):
  return PTZResolver(
    calibrations or {SOURCE_ID: CALIBRATION},
    lambda *args, **kwargs: published.append((args, kwargs)),
    poll_interval_s=0.2,
    max_pose_age_s=0.5,
    max_timestamp_uncertainty_s=0.01,
    target_reprojection_rms_px=3.0,
    sample_ring_buffer_size=ring_size,
    clock_ns=clock,
  )


def make_sample(sequence, timestamp_ns, pan=0.0, tilt=0.0, source_id=SOURCE_ID):
  sample = ptz_pb2.PTZSample(
    camera_id=source_id,
    adapter_instance_id="adapter-a",
    sequence=sequence,
    timestamp_uncertainty_ns=5_000_000,
    reported_move_status=ptz_pb2.REPORTED_MOVE_STATUS_IDLE,
  )
  sample.measured_at.FromNanoseconds(timestamp_ns)
  position = sample.position
  position.pan = pan
  position.tilt = tilt
  position.position_space_uri = MODEL.position_space.uri
  position.pan_min = MODEL.position_space.pan_min
  position.pan_max = MODEL.position_space.pan_max
  position.tilt_min = MODEL.position_space.tilt_min
  position.tilt_max = MODEL.position_space.tilt_max
  return sample


class TestPTZResolver(unittest.TestCase):
  def test_stationary_samples_publish_pose_context_after_full_settle_window(self):
    clock = FakeClock()
    published = []
    resolver = make_resolver(clock, published)
    result = None

    for sequence in range(1, 5):
      clock.timestamp_ns = START_NS + (sequence - 1) * 200_000_000
      result = resolver.submit_ptz_sample(make_sample(sequence, clock.timestamp_ns))

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED)
    self.assertEqual(len(published), 4)
    topic, payload = published[-1][0]
    self.assertEqual(topic, f"scenescape/positioning/pose/{SOURCE_ID}")
    self.assertEqual(published[-1][1], {"qos": 0, "retain": True})
    context = json.loads(payload)
    self.assertTrue(context["valid"])
    self.assertEqual(context["sequence"], 4)
    self.assertEqual(context["motion_state"], "stationary")
    self.assertEqual(context["pose"]["frame_id"], "scene:scene-a")
    np.testing.assert_allclose(context["pose"]["matrix_4x4"], HOME_MATRIX, atol=1e-12)
    self.assertEqual(set(context["quality"]), {
      "score", "temporal_score", "calibration_score", "reprojection_rms_px"})


  def test_invalid_position_space_is_rejected_without_pose_publication(self):
    clock = FakeClock()
    published = []
    resolver = make_resolver(clock, published)
    sample = make_sample(1, START_NS)
    sample.position.position_space_uri = "unexpected-space"

    result = resolver.submit_ptz_sample(sample)

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_INVALID)
    self.assertEqual(published, [])


  def test_stale_sample_publishes_expired_invalid_context(self):
    clock = FakeClock(START_NS + 700_000_000)
    published = []
    resolver = make_resolver(clock, published)

    result = resolver.submit_ptz_sample(make_sample(1, START_NS))

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED)
    context = json.loads(published[0][0][1])
    self.assertFalse(context["valid"])
    self.assertEqual(context["invalid_reason"], "pose_expired")
    self.assertEqual(context["reason_detail"], "sample_stale")
    self.assertNotIn("pose", context)


  def test_sequence_gap_resets_backlash_knowledge_and_invalidates_pose(self):
    clock = FakeClock()
    published = []
    resolver = make_resolver(clock, published)
    resolver.submit_ptz_sample(make_sample(1, START_NS))
    clock.timestamp_ns += 200_000_000

    result = resolver.submit_ptz_sample(make_sample(3, clock.timestamp_ns, pan=0.5))

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED)
    context = json.loads(published[-1][0][1])
    self.assertFalse(context["valid"])
    self.assertEqual(context["reason_detail"], "backlash_unknown")


  def test_measured_axis_change_publishes_slewing_invalid_context(self):
    clock = FakeClock()
    published = []
    resolver = make_resolver(clock, published)
    resolver.submit_ptz_sample(make_sample(1, START_NS))
    clock.timestamp_ns += 200_000_000

    result = resolver.submit_ptz_sample(make_sample(2, clock.timestamp_ns, pan=0.5))

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED)
    context = json.loads(published[-1][0][1])
    self.assertFalse(context["valid"])
    self.assertEqual(context["motion_state"], "slewing")
    self.assertEqual(context["reason_detail"], "moving")

  def test_resolved_pose_uses_backlash_corrected_physical_angles(self):
    clock = FakeClock()
    published = []
    resolver = make_resolver(clock, published)
    positions = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.0), (0.5, 0.0), (0.5, 0.0),
                 (0.5, 0.0)]
    for sequence, (pan, tilt) in enumerate(positions, start=1):
      clock.timestamp_ns = START_NS + (sequence - 1) * 200_000_000
      result = resolver.submit_ptz_sample(make_sample(sequence, clock.timestamp_ns, pan, tilt))

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_ACCEPTED)
    context = json.loads(published[-1][0][1])
    self.assertTrue(context["valid"])
    reported_pan = axis_angle_degrees(0.5, MODEL.pan.curve)
    home_pan = axis_angle_degrees(MODEL.pan.home_position, MODEL.pan.curve)
    physical_pan = apply_backlash(home_pan, reported_pan, 1.68)
    home_tilt = axis_angle_degrees(MODEL.tilt.home_position, MODEL.tilt.curve)
    home_rotation = Rotation.from_matrix(HOME_MATRIX[:3, :3])
    expected_rotation = compose_ptz_rotation(
      MODEL, home_rotation, physical_pan - home_pan, 0.0)
    actual_rotation = Rotation.from_matrix(np.asarray(context["pose"]["matrix_4x4"])[:3, :3])
    self.assertAlmostEqual(
      (expected_rotation.inv() * actual_rotation).magnitude(), 0.0, delta=1e-9)


  def test_unassigned_camera_is_not_published(self):
    clock = FakeClock()
    published = []
    resolver = make_resolver(clock, published)

    result = resolver.submit_ptz_sample(make_sample(1, START_NS, source_id="other-camera"))

    self.assertEqual(result.result, ptz_pb2.PTZ_SAMPLE_RESULT_UNKNOWN_CAMERA)
    self.assertEqual(published, [])


  def test_ring_buffer_must_cover_calibrated_backlash_history(self):
    with self.assertRaisesRegex(ValueError, "sample_ring_buffer_size must be >= 52"):
      make_resolver(FakeClock(), [], ring_size=51)

  def test_runtime_calibration_cannot_exceed_allocated_history(self):
    clock = FakeClock()
    resolver = make_resolver(clock, [])
    payload = copy.deepcopy(FIXTURE["ptz_calibration"])
    payload["axes"]["pan"]["backlash_history_s"] = 10.1
    changed = PTZSourceCalibration(load_ptz_model(payload), HOME_MATRIX, "scene:scene-a")

    with self.assertRaisesRegex(ValueError, "sample_ring_buffer_size must be >= 53"):
      resolver.update_calibration(SOURCE_ID, changed)

  def test_manager_calibration_loader_extracts_home_pose_and_scene_frame(self):
    camera = {
      "uid": SOURCE_ID,
      "ptz_calibration": FIXTURE["ptz_calibration"],
      "pose_matrix": HOME_MATRIX.tolist(),
      "scene": "scene-a",
    }
    manager = mock.Mock()
    manager.getCamera.return_value = type("CameraResult", (dict,), {"statusCode": 200})(camera)
    client_factory = mock.Mock(return_value=manager)
    loader = ManagerCalibrationLoader("https://manager/api/v1", "auth", "ca", client_factory)

    calibration = loader.load(SOURCE_ID)

    self.assertEqual(calibration.model.calibration_version, MODEL.calibration_version)
    self.assertEqual(calibration.frame_id, "scene:scene-a")
    np.testing.assert_allclose(calibration.home_matrix, HOME_MATRIX)
    client_factory.assert_called_once_with(
      "https://manager/api/v1", auth="auth", rootcert="ca", timeout=10)

  def test_manager_calibration_loader_rejects_different_camera_identity(self):
    camera = {"uid": "another-camera"}
    manager = mock.Mock()
    manager.getCamera.return_value = type("CameraResult", (dict,), {"statusCode": 200})(camera)
    loader = ManagerCalibrationLoader(
      "https://manager/api/v1", "auth", "ca", mock.Mock(return_value=manager))

    with self.assertRaises(ManagerCalibrationError):
      loader.load(SOURCE_ID)
