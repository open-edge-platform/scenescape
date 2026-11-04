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


@pytest.mark.test_name("NEX-T30943")
def test_ptz_detections_wait_for_the_dwell_and_use_the_pose_projection(
    ptz_harness, result_recorder):
  """
  ## Name
  PTZ Detections Wait For Dwell And Use Pose Projection

  ## Objective
  Verify that with PTZ enforcement enabled the Scene Controller admits no detection until the pose dwell completes, then projects detections with the published PoseContext instead of the static home pose.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera in the Demo scene, assigned to the test Positioning source
  2. Publish stationary PoseContexts for an off-home pose and start sending detections
  3. Wait until the Scene Controller outputs a scene message containing objects
  4. Verify the first admitted detection arrives no earlier than the minimum dwell after the first pose
  5. Verify the projected location matches the off-home pose projection and not the static home projection
  """
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


@pytest.mark.test_name("NEX-T30944")
def test_ptz_at_home_pose_matches_the_static_projection(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Home Pose Matches Static Projection

  ## Objective
  Verify that a PTZ camera publishing its home pose as a PoseContext projects detections to the same location as the static camera pose.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera in the Demo scene, assigned to the test Positioning source
  2. Publish stationary PoseContexts with the camera home pose and start sending detections
  3. Wait until the Scene Controller outputs a scene message containing objects
  4. Verify the projected location matches the static home projection within the tolerance
  """
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


@pytest.mark.test_name("NEX-T30945")
def test_ptz_slewing_blocks_detections_until_the_dwell_restarts(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Slewing Blocks Detections Until Dwell Restarts

  ## Objective
  Verify that detections of a slewing PTZ camera are dropped and resume only once the camera is stationary again and a new dwell has completed.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera, publish stationary poses and wait until detections are admitted
  2. Publish an invalid pose with the slewing motion state and reason detail `moving`
  3. Verify no detection reaches the scene output during the blackout window
  4. Publish a valid stationary pose again and clear the scene output
  5. Verify detections resume, and not before a new minimum dwell has elapsed since the restart
  """
  _assert_motion_blocks_until_dwell_restarts(ptz_harness, MOTION_SLEWING, "moving")
  result_recorder.success()


@pytest.mark.test_name("NEX-T30946")
def test_ptz_settling_blocks_detections_until_the_dwell_restarts(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Settling Blocks Detections Until Dwell Restarts

  ## Objective
  Verify that detections of a settling PTZ camera are dropped and resume only once the camera is stationary again and a new dwell has completed.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera, publish stationary poses and wait until detections are admitted
  2. Publish an invalid pose with the settling motion state and reason detail `settling`
  3. Verify no detection reaches the scene output during the blackout window
  4. Publish a valid stationary pose again and clear the scene output
  5. Verify detections resume, and not before a new minimum dwell has elapsed since the restart
  """
  _assert_motion_blocks_until_dwell_restarts(ptz_harness, MOTION_SETTLING, "settling")
  result_recorder.success()


@pytest.mark.test_name("NEX-T30947")
def test_ptz_stale_pose_drops_detections_and_recovers(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Stale Pose Drops Detections And Recovers

  ## Objective
  Verify that the Scene Controller stops admitting detections when poses stop arriving for longer than the maximum pose age, and admits them again once poses resume.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera, publish stationary poses and wait until detections are admitted
  2. Pause the pose publisher
  3. Verify no detection reaches the scene output for a period longer than the maximum pose age
  4. Resume the pose publisher and clear the scene output
  5. Verify detections are admitted again
  """
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


@pytest.mark.test_name("NEX-T30948")
def test_ptz_sequence_gap_resets_the_dwell(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Sequence Gap Resets Dwell

  ## Objective
  Verify that a gap in the pose sequence numbers restarts the dwell, since the camera may have moved while samples were missing.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera, publish stationary poses and wait until detections are admitted
  2. Skip three sequence numbers in the published poses
  3. Drain the output of detections admitted before the gap and clear the scene output
  4. Verify no detection is admitted while the new dwell is incomplete
  5. Verify detections resume, and not before a new minimum dwell has elapsed since the gap
  """
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  _assert_dwell_restarts(harness, lambda: publisher.skip_sequence(3))
  result_recorder.success()


@pytest.mark.test_name("NEX-T30949")
def test_ptz_resolver_session_change_resets_the_dwell(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Resolver Session Change Resets Dwell

  ## Objective
  Verify that a new Resolver session invalidates the accumulated dwell even though poses keep arriving.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera, publish stationary poses and wait until detections are admitted
  2. Start a new Resolver session in the pose publisher
  3. Drain the output of detections admitted before the change and clear the scene output
  4. Verify no detection is admitted while the new dwell is incomplete
  5. Verify detections resume, and not before a new minimum dwell has elapsed since the change
  """
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  harness.wait_for_admission()

  _assert_dwell_restarts(harness, publisher.new_session)
  result_recorder.success()


@pytest.mark.test_name("NEX-T30950")
def test_ptz_frame_or_calibration_mismatch_drops_detections(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Frame Or Calibration Mismatch Drops Detections

  ## Objective
  Verify that poses for another frame or another calibration version never admit detections.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera, publish stationary poses and wait until detections are admitted
  2. Publish poses with the frame id of another scene
  3. Verify no detection reaches the scene output during the blackout window
  4. Publish poses with the matching frame id and verify detections resume
  5. Publish poses with a stale calibration version
  6. Verify no detection reaches the scene output during the blackout window
  """
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


@pytest.mark.test_name("NEX-T30951")
def test_ptz_camera_without_resolver_assignment_fails_closed(ptz_harness, result_recorder):
  """
  ## Name
  PTZ Camera Without Resolver Assignment Fails Closed

  ## Objective
  Verify that detections of a PTZ camera missing from the Resolver assignment manifest are dropped while static cameras in the same scene keep tracking.

  ## Labels
  - Functional

  ## Steps
  1. Create a PTZ camera that has no Resolver assignment
  2. Send detections for the unassigned camera
  3. Verify no detection reaches the scene output during the blackout window
  4. Clear the scene output and send detections for the static Demo camera
  5. Verify the static Demo camera detections are still tracked
  """
  harness = ptz_harness
  harness.create_ptz_camera(ORPHAN_CAMERA_ID)

  harness.assert_blackout(BLACKOUT_S, camera_id=ORPHAN_CAMERA_ID)

  harness.clear_output()
  assert harness.run_detections(
    RESUME_TIMEOUT_S, camera_id=DEMO_CAMERA_ID, until=lambda: _admitted(harness)), \
    "the static Demo camera stopped tracking while a PTZ camera was unassigned"
  result_recorder.success()
