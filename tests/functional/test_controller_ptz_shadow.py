#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene Controller PTZ pose consumption in shadow mode (CONTROLLER_PTZ_SHADOW_MODE).

Shadow mode observes: tracking keeps using the static home pose and every PTZ decision,
with the candidate projection and its residual against the static one, is written as a
JSONL record to the Controller logs.
"""

import time

import numpy as np
import pytest

from tests.functional.ptz_controller_harness import (  # noqa: F401 (fixture)
  LOCATION_TOLERANCE_M, ptz_harness)
from tests.functional.ptz_pose_publisher import MOTION_SLEWING, SOURCE_ID
from tests.utils.log import get_logger
from tests.utils.profiles import PTZ_SHADOW
from tests.utils.ptz_shadow import parse_shadow_records, write_shadow_artifact
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=PTZ_SHADOW,
  auth=AUTH_CONTROLLER,
)

RUN_ID = "functional-shadow"
RECORD_TIMEOUT_S = 30.0
REQUIRED_FIELDS = (
  "record_type", "profile", "mode", "run_id", "scene_id", "source_id", "sequence",
  "calibration_version", "observation_timestamp", "pose_age_s", "timestamp_uncertainty_s",
  "dwell_elapsed_s", "admitted", "invalid_reason", "reason_detail", "detections")


def shadow_records(scenescape_env):
  """Shadow records of this run and source from the Controller container's stdout."""
  container = f"{scenescape_env.project_name}-scene-1"
  text = scenescape_env.docker.container.logs(container)
  return [record for record in parse_shadow_records(text, RUN_ID)
          if record["source_id"] == SOURCE_ID]


def wait_for_record(scenescape_env, harness, predicate, timeout=RECORD_TIMEOUT_S):
  """Keep sending detections until a record satisfies `predicate`; returns the records."""
  deadline = time.time() + timeout
  while time.time() < deadline:
    harness.run_detections(1.0)
    records = shadow_records(scenescape_env)
    if any(predicate(record) for record in records):
      return records
  raise AssertionError(f"No matching shadow record within {timeout}s: {shadow_records(scenescape_env)[-3:]}")


@pytest.mark.test_name("NEX-T29970")
def test_shadow_mode_keeps_the_static_projection_and_records_the_candidate(
    scenescape_env, ptz_harness, tmp_path, result_recorder):
  """Tracking stays on the static pose while the candidate projection is recorded."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  off_home = harness.off_home_matrix_for(camera)
  expected_home = harness.expected_location(camera["pose_matrix"])
  expected_pose = harness.expected_location(off_home)
  assert np.linalg.norm(expected_pose - expected_home) > 2 * LOCATION_TOLERANCE_M

  harness.start_poses(camera, matrix=off_home)
  harness.wait_for_admission()
  assert np.linalg.norm(harness.latest_location() - expected_home) <= LOCATION_TOLERANCE_M, \
    "shadow mode must keep projecting with the static home pose"

  records = wait_for_record(
    scenescape_env, harness, lambda r: r["admitted"] and r["detections"])
  for record in records:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    assert not missing, f"record lacks {missing}"
    assert record["profile"] == "controller" and record["mode"] == "shadow"
    assert record["scene_id"] == harness.scene_uid

  rejected = [r for r in records if not r["admitted"]]
  assert rejected and rejected[0]["reason_detail"] in ("no_sample", "dwell_incomplete"), \
    "the detections sent before the dwell completed must be recorded as rejected"

  admitted = next(r for r in records if r["admitted"] and r["detections"])
  assert admitted["calibration_version"] == "ptz-functional-v1"
  assert admitted["dwell_elapsed_s"] >= 1.0 and admitted["pose_age_s"] < 0.5
  detection = admitted["detections"][0]
  assert np.linalg.norm(np.array(detection["static_xyz"][:2]) - expected_home) \
    <= LOCATION_TOLERANCE_M
  assert np.linalg.norm(np.array(detection["candidate_xyz"][:2]) - expected_pose) \
    <= LOCATION_TOLERANCE_M
  assert detection["residual_m"] > LOCATION_TOLERANCE_M

  artifact = write_shadow_artifact(shadow_records(scenescape_env), RUN_ID, root=tmp_path)
  assert artifact.name == f"{RUN_ID}.jsonl" and artifact.read_text().strip()
  result_recorder.success()


@pytest.mark.test_name("NEX-T29971")
def test_shadow_mode_does_not_gate_detections_of_a_moving_camera(
    scenescape_env, ptz_harness, result_recorder):
  """A moving PTZ camera is recorded as rejected but its detections still reach tracking."""
  harness = ptz_harness
  camera = harness.create_ptz_camera()
  publisher = harness.start_poses(camera)
  publisher.set_pose(valid=False, motion_state=MOTION_SLEWING, reason_detail="moving")

  harness.wait_for_admission()

  records = wait_for_record(
    scenescape_env, harness, lambda r: r["reason_detail"] == "moving")
  moving = [r for r in records if r["reason_detail"] == "moving"]
  assert all(not r["admitted"] and r["invalid_reason"] == "invalid_pose" for r in moving)
  result_recorder.success()
