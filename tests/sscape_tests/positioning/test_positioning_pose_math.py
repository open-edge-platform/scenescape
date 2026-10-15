# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PTZ pose math against the provisional (non-golden) PoC fixture and analytic properties."""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from positioning.pose_math import (
  apply_backlash, axis_angle_degrees, axis_rotation, backlash_degrees_at,
  compose_ptz_rotation, rotation_delta_magnitude, rotation_from_ptz_delta,
  scene_from_camera_matrix)
from positioning.ptz_model import load_ptz_model

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads(
  (REPO_ROOT / "tests" / "data" / "ptz" / "provisional_pose_math.json").read_text())
MODEL = load_ptz_model(FIXTURE["ptz_calibration"])
HOME = Rotation.from_euler("XYZ", FIXTURE["home_pose"]["rotation_euler_xyz_deg"], degrees=True)
HOME_TRANSLATION = FIXTURE["home_pose"]["translation_m"]


def test_fixture_is_marked_provisional():
  assert FIXTURE["provisional"] is True


@pytest.mark.parametrize("vector", FIXTURE["curve_vectors"])
def test_curve_vectors(vector):
  curve = MODEL.axis_spec(vector["axis"]).curve
  assert axis_angle_degrees(vector["position"], curve) == pytest.approx(vector["expected_deg"])


@pytest.mark.parametrize("vector", FIXTURE["backlash_vectors"])
def test_backlash_vectors(vector):
  backlash = MODEL.axis_spec(vector["axis"]).backlash
  assert backlash_degrees_at(backlash, vector["position"]) == pytest.approx(vector["expected_deg"])


def test_backlash_scalar_and_negative_clamped():
  assert backlash_degrees_at(2.73, 0.9) == 2.73
  assert backlash_degrees_at(-1.0, 0.0) == 0.0
  assert backlash_degrees_at(None, 0.0) == 0.0


def test_apply_backlash_deadband():
  assert apply_backlash(None, 10.0, 2.0) == 10.0
  assert apply_backlash(9.5, 10.0, 0.0) == 10.0
  assert apply_backlash(9.5, 10.0, 2.0) == 9.5
  assert apply_backlash(8.0, 10.0, 2.0) == 9.0
  assert apply_backlash(12.0, 10.0, 2.0) == 11.0


def test_at_home_reproduces_static_pose():
  rotation, delta_pan, delta_tilt = rotation_from_ptz_delta(
    MODEL, HOME, MODEL.pan.home_position, MODEL.tilt.home_position)
  assert delta_pan == 0.0 and delta_tilt == 0.0
  assert rotation_delta_magnitude(rotation, HOME) == pytest.approx(0.0, abs=1e-9)


def test_world_axis_pan_is_height_preserving_and_shifts_azimuth():
  model = load_ptz_model(_with_axis(FIXTURE["ptz_calibration"], "pan", [0.0, 0.0, 1.0]))
  rotation = compose_ptz_rotation(model, HOME, 20.0, 0.0)
  before = HOME.as_matrix()[:, 2]
  after = rotation.as_matrix()[:, 2]
  assert after[2] == pytest.approx(before[2], abs=1e-12)
  azimuth = np.degrees(np.arctan2(after[1], after[0]) - np.arctan2(before[1], before[0]))
  assert (azimuth + 180.0) % 360.0 - 180.0 == pytest.approx(20.0, abs=1e-9)


def test_camera_local_tilt_keeps_camera_x_and_rotates_optical_axis():
  rotation = compose_ptz_rotation(MODEL, HOME, 0.0, 15.0)
  np.testing.assert_allclose(rotation.as_matrix()[:, 0], HOME.as_matrix()[:, 0], atol=1e-12)
  cos_angle = np.dot(rotation.as_matrix()[:, 2], HOME.as_matrix()[:, 2])
  assert np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))) == pytest.approx(15.0, abs=1e-9)


def test_naive_euler_addition_diverges_from_matrix_composition():
  model = load_ptz_model(_with_axis(FIXTURE["ptz_calibration"], "pan", [0.0, 0.0, 1.0]))
  composed = compose_ptz_rotation(model, HOME, 20.0, 0.0)
  naive = Rotation.from_euler(
    "XYZ", np.array(FIXTURE["home_pose"]["rotation_euler_xyz_deg"]) + [0.0, 0.0, 20.0],
    degrees=True)
  assert rotation_delta_magnitude(naive, composed) > 5.0


def test_composition_matches_poc_formula():
  """PoC: R_new = R_pan(axis) @ R_home @ Rx(tilt)."""
  delta_pan, delta_tilt = -31.0, 12.5
  pan_axis = np.array(MODEL.pan.axis)
  expected = (Rotation.from_rotvec(np.radians(delta_pan) * pan_axis / np.linalg.norm(pan_axis))
              * HOME * Rotation.from_euler("x", delta_tilt, degrees=True))
  actual = compose_ptz_rotation(MODEL, HOME, delta_pan, delta_tilt)
  assert rotation_delta_magnitude(actual, expected) == pytest.approx(0.0, abs=1e-9)


def test_composition_order_is_honoured():
  payload = json.loads(json.dumps(FIXTURE["ptz_calibration"]))
  payload["composition_order"] = ["home", "pan", "tilt"]
  payload["axes"]["pan"]["frame"] = "camera_local"
  payload["axes"]["pan"]["axis"] = [0.0, 1.0, 0.0]
  model = load_ptz_model(payload)
  expected = (HOME * Rotation.from_euler("y", 10.0, degrees=True)
              * Rotation.from_euler("x", 5.0, degrees=True))
  actual = compose_ptz_rotation(model, HOME, 10.0, 5.0)
  assert rotation_delta_magnitude(actual, expected) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("axis,name", [([1, 0, 0], "x"), ([0, 1, 0], "y"), ([0, 0, 1], "z")])
def test_axis_rotation_reduces_to_axis_aligned(axis, name):
  assert rotation_delta_magnitude(
    axis_rotation(axis, 33.0), Rotation.from_euler(name, 33.0, degrees=True)) == pytest.approx(
      0.0, abs=1e-9)


def test_rotation_delta_magnitude():
  a = Rotation.from_euler("XYZ", [10, 20, 30], degrees=True)
  b = a * Rotation.from_euler("z", 7.5, degrees=True)
  assert rotation_delta_magnitude(a, b) == pytest.approx(7.5)


def test_scene_from_camera_matrix_row_major_rigid_and_translation_unchanged():
  rotation, _, _ = rotation_from_ptz_delta(MODEL, HOME, 0.3, -0.2)
  matrix = scene_from_camera_matrix(rotation, HOME_TRANSLATION)
  assert matrix.shape == (4, 4)
  np.testing.assert_array_equal(matrix[3], [0, 0, 0, 1])
  np.testing.assert_allclose(matrix[:3, 3], HOME_TRANSLATION)
  np.testing.assert_allclose(matrix[:3, :3] @ matrix[:3, :3].T, np.eye(3), atol=1e-12)
  assert np.linalg.det(matrix[:3, :3]) == pytest.approx(1.0)


def test_generated_protobuf_stubs():
  # pylint: disable=no-member  # protobuf builds message classes at runtime
  from positioning.v1 import ptz_pb2, ptz_pb2_grpc

  sample = ptz_pb2.PTZSample(camera_id="atag-ptzcam3", adapter_instance_id="a1", sequence=7,
                             timestamp_uncertainty_ns=5_000_000,
                             reported_move_status=ptz_pb2.REPORTED_MOVE_STATUS_IDLE)
  sample.position.pan = 0.25
  sample.measured_at.FromNanoseconds(1_790_000_000_123_000_000)
  decoded = ptz_pb2.PTZSample.FromString(sample.SerializeToString())
  assert decoded == sample
  assert not decoded.position.HasField("zoom")
  assert ptz_pb2.DESCRIPTOR.package == "scenescape.ptz.v1"
  assert [f.name for f in ptz_pb2.PTZSample.DESCRIPTOR.fields] == [
    "camera_id", "adapter_instance_id", "sequence", "measured_at", "timestamp_uncertainty_ns",
    "position", "reported_move_status"]
  assert hasattr(ptz_pb2_grpc, "PTZPoseIngestServicer")


def _with_axis(payload, axis_name, axis):
  copy = json.loads(json.dumps(payload))
  copy["axes"][axis_name]["axis"] = axis
  return copy
