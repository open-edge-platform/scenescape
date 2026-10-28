#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene Controller PTZ pose consumption in enforcing mode (CONTROLLER_PTZ_ENABLED).

PoseContexts are published through the broker as the Positioning identity; detections
are published on the camera topic. The tests assert what reaches the tracker through
the scene output: nothing while a pose is moving, settling, stale, mismatched, or its
dwell is incomplete, and projection with the PoseContext once the dwell completes.
"""

import time

import numpy as np
import pytest

from tests.functional.ptz_controller_harness import (  # noqa: F401 (fixture)
  DEMO_CAMERA_ID, LOCATION_TOLERANCE_M, MIN_DWELL_S, ptz_harness)
from tests.functional.ptz_pose_publisher import MOTION_SETTLING, MOTION_SLEWING
from tests.utils.log import get_logger
from tests.utils.profiles import PTZ_ENFORCE
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=PTZ_ENFORCE,
  auth=AUTH_CONTROLLER,
)

# Longer than max_pose_age_s (0.5 s) and shorter than the dwell bound (1 s)
BLACKOUT_S = 2.0
RESUME_TIMEOUT_S = 15.0
DRAIN_S = 0.4
ORPHAN_CAMERA_ID = "ptz-unassigned"


def _admitted(harness):
  return bool(harness.output_with_objects())


@pytest.mark.test_name("NEX-T29961")
def test_ptz_detections_wait_for_the_dwell_and_use_the_pose_projection(
    ptz_harness, result_recorder):
  """No detection is admitted before the dwell completes, then it projects with the pose."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  off_home = harness.off_home_matrix_for(camera)
  expected_home = harness.expected_location(camera["pose_matrix"])
  expected_pose = harness.expected_location(off_home)
  assert np.linalg.norm(expected_pose - expected_home) > 2 * LOCATION_TOLERANCE_M, \
    "the off-home pose must move the projection clearly away from the home projection"

  harness.start_poses(camera, matrix=off_home)
  admitted_at = harness.wait_for_admission()

  assert admitted_at - harness.poses_started >= MIN_DWELL_S, \
    "a detection was admitted before the dwell could have completed"
  location = harness.latest_location()
  assert np.linalg.norm(location - expected_pose) <= LOCATION_TOLERANCE_M, \
    f"projected {location}, expected the pose projection {expected_pose}"
  assert np.linalg.norm(location - expected_home) > LOCATION_TOLERANCE_M, \
    "the detection was projected with the static home pose"
  result_recorder.success()


@pytest.mark.test_name("NEX-T29962")
def test_ptz_at_home_pose_matches_the_static_projection(ptz_harness, result_recorder):
  """The home pose published as a PoseContext projects like the static camera pose."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  expected_home = harness.expected_location(camera["pose_matrix"])

  harness.start_poses(camera)
  harness.wait_for_admission()

  location = harness.latest_location()
  assert np.linalg.norm(location - expected_home) <= LOCATION_TOLERANCE_M, \
    f"projected {location}, expected the static projection {expected_home}"
  result_recorder.success()


def _assert_motion_blocks_until_dwell_restarts(harness, state, reason):
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  publisher.set_pose(valid=False, motion_state=state, reason_detail=reason)
  harness.assert_blackout(BLACKOUT_S)

  restart = time.time()
  publisher.set_pose(valid=True, motion_state="stationary")
  harness.clear_output()
  assert harness.run_detections(RESUME_TIMEOUT_S, until=lambda: _admitted(harness)), \
    "detections did not resume after the camera became stationary again"
  assert harness.output_with_objects()[0][0] - restart >= MIN_DWELL_S, \
    "detections resumed before a new dwell could have completed"


@pytest.mark.test_name("NEX-T29963")
def test_ptz_slewing_blocks_detections_until_the_dwell_restarts(ptz_harness, result_recorder):
  """A moving camera drops detections; they resume only after a new dwell."""
  _assert_motion_blocks_until_dwell_restarts(ptz_harness, MOTION_SLEWING, "moving")
  result_recorder.success()


@pytest.mark.test_name("NEX-T29969")
def test_ptz_settling_blocks_detections_until_the_dwell_restarts(ptz_harness, result_recorder):
  """A settling camera drops detections; they resume only after a new dwell."""
  _assert_motion_blocks_until_dwell_restarts(ptz_harness, MOTION_SETTLING, "settling")
  result_recorder.success()


@pytest.mark.test_name("NEX-T29964")
def test_ptz_stale_pose_drops_detections_and_recovers(ptz_harness, result_recorder):
  """Without fresh poses the Controller stops admitting; it recovers after a new dwell."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  publisher.pause()
  harness.assert_blackout(BLACKOUT_S)

  publisher.resume()
  harness.clear_output()
  assert harness.run_detections(RESUME_TIMEOUT_S, until=lambda: _admitted(harness)), \
    "detections did not resume after the poses resumed"
  result_recorder.success()


def _assert_dwell_restarts(harness, trigger):
  """`trigger` resets the dwell: nothing is admitted for the first part of the new dwell."""
  triggered_at = time.time()
  trigger()
  # Drain output of detections admitted before the trigger, which may still be in flight
  harness.run_detections(DRAIN_S)
  harness.clear_output()
  harness.run_detections(DRAIN_S)
  assert not _admitted(harness), "a detection was admitted while the new dwell was incomplete"
  assert harness.run_detections(RESUME_TIMEOUT_S, until=lambda: _admitted(harness)), \
    "detections did not resume after the dwell restarted"
  assert harness.output_with_objects()[0][0] - triggered_at >= MIN_DWELL_S * 0.95, \
    "detections resumed before a new dwell could have completed"


@pytest.mark.test_name("NEX-T29965")
def test_ptz_sequence_gap_resets_the_dwell(ptz_harness, result_recorder):
  """A missing sample means the camera may have moved: the dwell restarts."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  _assert_dwell_restarts(harness, lambda: publisher.skip_sequence(3))
  result_recorder.success()


@pytest.mark.test_name("NEX-T29966")
def test_ptz_resolver_session_change_resets_the_dwell(ptz_harness, result_recorder):
  """A new Resolver session invalidates the accumulated dwell even if poses continue."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  _assert_dwell_restarts(harness, publisher.new_session)
  result_recorder.success()


@pytest.mark.test_name("NEX-T29967")
def test_ptz_frame_or_calibration_mismatch_drops_detections(ptz_harness, result_recorder):
  """Poses for another frame or calibration version never admit detections."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  publisher.set_pose(frame_id="scene:another-scene")
  harness.assert_blackout(BLACKOUT_S)
  publisher.set_pose(frame_id=harness.frame_id)
  assert harness.run_detections(RESUME_TIMEOUT_S, until=lambda: _admitted(harness)), \
    "detections did not resume once the frame matched again"

  publisher.set_pose(calibration_version="stale-calibration")
  harness.assert_blackout(BLACKOUT_S)
  result_recorder.success()


@pytest.mark.test_name("NEX-T29968")
def test_ptz_camera_without_resolver_assignment_fails_closed(ptz_harness, result_recorder):
  """A PTZ camera missing from the assignment manifest is dropped; static cameras still track."""
  harness = ptz_harness
  harness.create_ptz_camera(ORPHAN_CAMERA_ID)

  harness.assert_blackout(BLACKOUT_S, camera_id=ORPHAN_CAMERA_ID)

  harness.clear_output()
  assert harness.run_detections(
    RESUME_TIMEOUT_S, camera_id=DEMO_CAMERA_ID, until=lambda: _admitted(harness)), \
    "the static Demo camera stopped tracking while a PTZ camera was unassigned"
  result_recorder.success()
