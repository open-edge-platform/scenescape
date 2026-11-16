# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Phase 6 hardware acceptance replay against tests/data/ptz/reprojection_golden.json.

The golden dataset is a held-out hardware measurement of the Positioning service on a real
PTZ camera. These tests need no hardware: they recompute every accuracy metric with the
Controller's projection code, replay the logged ONVIF samples through the production
Resolver, and check the results against tests/data/ptz/acceptance_profile.json.
"""

import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from positioning.ptz_model import load_ptz_model
from positioning.ptz_poller import build_sample
from positioning.ptz_resolver import PTZResolver, PTZSourceCalibration
from positioning.v1 import ptz_pb2
from scene_common.geometry import Point
from scene_common.schema import SchemaValidation
from scene_common.transform import CameraIntrinsics, CameraPose

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "tests" / "data" / "ptz"
GOLDEN = json.loads((DATA / "reprojection_golden.json").read_text())
PROFILE = json.loads((DATA / "acceptance_profile.json").read_text())["profiles"]["controller-enforce"]
THRESHOLDS = PROFILE["thresholds"]
CALIBRATION = GOLDEN["calibration"]
STOPS = GOLDEN["stops"]
SAMPLE_PERIOD_NS = 50_000_000
SETTLE_SAMPLES = 20
MOVE_STATUS = {"MOVING": ptz_pb2.REPORTED_MOVE_STATUS_MOVING,
               "IDLE": ptz_pb2.REPORTED_MOVE_STATUS_IDLE}


def _nearest_rank(values, fraction):
  ordered = sorted(values)
  return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _intrinsics():
  return CameraIntrinsics(CALIBRATION["intrinsics"], CALIBRATION["distortion"])


def _controller_errors(stop, intrinsics):
  """Pixel and ground-plane error of each tag through the Controller's CameraPose."""
  pose = CameraPose(np.array(stop["pose_context"]["pose"]["matrix_4x4"]), intrinsics)
  rows = []
  for pixel, point in zip(stop["points_2d"], stop["points_3d"]):
    projected = pose.projectWorldPointToCameraPixels(Point(*point))
    ground = pose.cameraPointToWorldPoint(
      intrinsics.mapPixelToNormalizedImagePlane(Point(*pixel)))
    rows.append((math.hypot(projected.x - pixel[0], projected.y - pixel[1]),
                 math.hypot(ground.x - point[0], ground.y - point[1])))
  return rows


@pytest.fixture(scope="module")
def controller_errors():
  intrinsics = _intrinsics()
  return [_controller_errors(stop, intrinsics) for stop in STOPS]


def _replay():
  """Feed the logged ONVIF samples through the production Resolver, one pose per stop.

  The camera stayed parked between a stop's trace and the next move while AprilTags were
  captured, so those gaps are filled with stationary samples like the live poller's.
  """
  model = load_ptz_model(CALIBRATION["ptz_calibration"])
  calibration = PTZSourceCalibration(model, CALIBRATION["home_pose_matrix"],
                                     CALIBRATION["frame_id"])
  positioning = GOLDEN["positioning"]
  published, now = [], [0]
  resolver = PTZResolver(
    {"cam": calibration}, lambda _topic, payload, **_: published.append(json.loads(payload)),
    poll_interval_s=positioning["poll_interval_s"], max_pose_age_s=positioning["max_pose_age_s"],
    max_timestamp_uncertainty_s=positioning["max_timestamp_uncertainty_s"],
    target_reprojection_rms_px=positioning["target_reprojection_rms_px"],
    sample_ring_buffer_size=positioning["sample_ring_buffer_size"], clock_ns=lambda: now[0])
  resolver.update_calibration("cam", calibration)
  sequence = 0

  def submit(t_ns, pan, tilt, status):
    nonlocal sequence
    sequence += 1
    now[0] = t_ns + 5_000_000
    resolver.submit_ptz_sample(build_sample(
      "cam", "golden-replay", sequence, t_ns, 5_000_000,
      SimpleNamespace(pan=pan, tilt=tilt, zoom=None, space_uri=None),
      model.position_space, MOVE_STATUS.get(status, ptz_pb2.REPORTED_MOVE_STATUS_UNSPECIFIED)))
    return published[-1]

  position = tuple(GOLDEN["start_position"])
  t_ns = STOPS[0]["onvif_trace"][0][0] - (SETTLE_SAMPLES + 1) * SAMPLE_PERIOD_NS
  for _ in range(SETTLE_SAMPLES):
    t_ns += SAMPLE_PERIOD_NS
    submit(t_ns, *position, "IDLE")
  results = []
  for stop in STOPS:
    while t_ns + SAMPLE_PERIOD_NS < stop["onvif_trace"][0][0]:
      t_ns += SAMPLE_PERIOD_NS
      submit(t_ns, *position, "IDLE")
    during_motion = []
    for t_ns, pan, tilt, status in stop["onvif_trace"]:
      context = submit(t_ns, pan, tilt, status)
      if status == "MOVING":
        during_motion.append(context)
    position = (stop["onvif_trace"][-1][1], stop["onvif_trace"][-1][2])
    for _ in range(SETTLE_SAMPLES):
      t_ns += SAMPLE_PERIOD_NS
      settled = submit(t_ns, *position, "IDLE")
    results.append({"settled": settled, "during_motion": during_motion})
  return results


@pytest.fixture(scope="module")
def replay():
  return _replay()


def test_golden_is_a_held_out_hardware_measurement():
  provenance, coverage = GOLDEN["provenance"], GOLDEN["coverage"]
  ptz_calibration = CALIBRATION["ptz_calibration"]

  assert coverage["acceptance_eligible"] is True
  assert coverage["held_out_validation"] is True
  assert provenance["images_included"] is False
  assert set(provenance["camera"]) == {"model"}
  assert provenance["calibration_version"] == ptz_calibration["calibration_version"]
  assert provenance["calibration_sha256"] == hashlib.sha256(json.dumps(
    ptz_calibration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
  assert coverage["stops"] == len(STOPS)
  assert coverage["matched_points"] == sum(len(stop["points_2d"]) for stop in STOPS)
  assert all(len(stop["points_2d"]) == len(stop["points_3d"]) > 0 for stop in STOPS)


def test_golden_covers_both_directions_and_dual_axis_sweeps():
  directions = GOLDEN["coverage"]["directions"]
  for key in ("pan:up/-", "pan:down/-", "tilt:-/up", "tilt:-/down",
              "both:up/up", "both:up/down", "both:down/up", "both:down/down"):
    assert directions.get(key, 0) >= 2, key
  assert GOLDEN["coverage"]["repetitions"] >= 2


def test_golden_was_measured_with_the_profile_configuration():
  applies_to = PROFILE["applies_to"]
  assert GOLDEN["positioning"]["poll_interval_s"] == applies_to["positioning_poll_interval_s"]
  assert GOLDEN["positioning"]["source"]["move_status"] == applies_to["move_status"]


def test_published_poses_are_schema_valid_and_stationary():
  schema = SchemaValidation(str(REPO_ROOT / "controller/src/schema/metadata.schema.json"),
                            is_multi_message=True)
  for stop in STOPS:
    context = stop["pose_context"]
    assert schema.validateMessage("pose_context", context, check_format=True), stop["index"]
    assert context["valid"] and context["motion_state"] == "stationary"
    assert context["calibration_version"] == CALIBRATION["ptz_calibration"]["calibration_version"]
    assert context["pose"]["frame_id"] == CALIBRATION["frame_id"]
    assert stop["pose_stable_during_capture"]


def test_stored_residuals_match_the_controller_projection(controller_errors):
  for stop, errors in zip(STOPS, controller_errors):
    for stored, (pixel_px, _ground_m) in zip(stop["residuals"], errors):
      assert stored[0] == pytest.approx(pixel_px, abs=1e-5), stop["index"]


def test_spatial_error_meets_profile(controller_errors):
  ground = [ground_m for errors in controller_errors for _, ground_m in errors]
  limit = THRESHOLDS["ground_plane_error_m"]
  assert _nearest_rank(ground, 0.95) <= limit["p95_max"]
  assert max(ground) <= limit["max_max"]


def test_reprojection_error_meets_profile(controller_errors):
  pixels = [pixel_px for errors in controller_errors for pixel_px, _ in errors]
  limit = THRESHOLDS["reprojection_px"]
  assert _nearest_rank(pixels, 0.95) <= limit["p95_max"]
  assert max(pixels) <= limit["max_max"]
  assert GOLDEN["metrics"]["reprojection_px"]["p95"] == pytest.approx(
    _nearest_rank(pixels, 0.95), abs=1e-5)


def test_pose_latency_meets_profile():
  latency = GOLDEN["metrics"]["pose_latency_s"]
  limit = THRESHOLDS["pose_latency_s"]
  assert latency["count"] > 1000
  assert latency["p95"] <= limit["p95_max"]
  assert latency["max"] <= limit["max_max"]
  assert latency["max"] < GOLDEN["positioning"]["max_pose_age_s"]


def test_post_motion_availability_meets_profile():
  available = [(stop["first_valid_pose"]["received_ns"] - stop["stopped_ns"]) / 1e9
               for stop in STOPS]
  limit = THRESHOLDS["post_motion_availability_s"]
  # The stop is timestamped from the measurement's own GetStatus polls, so the Resolver
  # may have seen the last motion up to one poll period of each earlier.
  resolution_s = (GOLDEN["measurement_settings"]["status_period_s"]
                  + GOLDEN["positioning"]["poll_interval_s"])
  assert min(available) >= CALIBRATION["ptz_calibration"]["settle_interval_s"] - resolution_s
  assert _nearest_rank(available, 0.95) < limit["p95_below"]
  assert max(available) < limit["max_below"]


def test_no_valid_pose_was_sampled_while_moving_on_hardware():
  assert GOLDEN["metrics"]["valid_poses_sampled_during_motion"] <= (
    THRESHOLDS["valid_poses_sampled_during_motion"]["max"])
  assert GOLDEN["metrics"]["pose_changed_during_capture"] == 0


def test_repeated_stops_resolve_to_the_same_pose():
  limit = THRESHOLDS["repeatability"]
  per_repetition = len(STOPS) // GOLDEN["coverage"]["repetitions"]
  for later in STOPS[per_repetition:]:
    earlier = STOPS[later["index"] - 1 - per_repetition]
    assert earlier["target"] == later["target"]
    np.testing.assert_allclose(later["pose_context"]["pose"]["matrix_4x4"],
                               earlier["pose_context"]["pose"]["matrix_4x4"],
                               rtol=0, atol=limit["max_abs_pose_matrix_difference"])
  assert GOLDEN["metrics"]["repeatability"]["max_abs_mean_pixel_difference_px"] <= (
    limit["max_abs_mean_pixel_difference_px"])


def test_resolver_replay_reproduces_every_hardware_pose(replay):
  for stop, result in zip(STOPS, replay):
    settled = result["settled"]
    assert settled["valid"] and settled["motion_state"] == "stationary", stop["index"]
    assert settled["calibration_version"] == stop["pose_context"]["calibration_version"]
    np.testing.assert_allclose(settled["pose"]["matrix_4x4"],
                               stop["pose_context"]["pose"]["matrix_4x4"], rtol=0, atol=1e-12)


def test_resolver_replay_never_validates_a_moving_sample(replay):
  moving = [context for result in replay for context in result["during_motion"]]
  assert moving
  assert not any(context["valid"] for context in moving)


def test_resolver_replay_is_deterministic(replay):
  assert _replay() == replay
