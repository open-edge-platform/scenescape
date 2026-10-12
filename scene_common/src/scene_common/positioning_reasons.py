# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Canonical positioning failure reasons and the PTZ reason_detail mapping.

The three canonical values duplicate controller.external_source literals
(scene_common must not import controller); a unit test guards against drift.
"""

REASON_NO_POSE_AVAILABLE = "no_pose_available"
REASON_POSE_EXPIRED = "pose_expired"
REASON_INVALID_POSE = "invalid_pose"

CANONICAL_REASONS = frozenset({
  REASON_NO_POSE_AVAILABLE,
  REASON_POSE_EXPIRED,
  REASON_INVALID_POSE,
})

# Resolver-published PTZ reason_detail values (PoseContext.reason_detail).
DETAIL_NO_SAMPLE = "no_sample"
DETAIL_SAMPLE_STALE = "sample_stale"
DETAIL_MOVING = "moving"
DETAIL_SETTLING = "settling"
DETAIL_CALIBRATION_MISSING = "calibration_missing"
DETAIL_CALIBRATION_CHANGED = "calibration_changed"
DETAIL_INVALID_SAMPLE = "invalid_sample"
DETAIL_BACKLASH_UNKNOWN = "backlash_unknown"

PTZ_REASON_DETAILS = {
  DETAIL_NO_SAMPLE: REASON_NO_POSE_AVAILABLE,
  DETAIL_SAMPLE_STALE: REASON_POSE_EXPIRED,
  DETAIL_MOVING: REASON_INVALID_POSE,
  DETAIL_SETTLING: REASON_INVALID_POSE,
  DETAIL_CALIBRATION_MISSING: REASON_INVALID_POSE,
  DETAIL_CALIBRATION_CHANGED: REASON_INVALID_POSE,
  DETAIL_INVALID_SAMPLE: REASON_INVALID_POSE,
  DETAIL_BACKLASH_UNKNOWN: REASON_INVALID_POSE,
}

# Consumer-side dwell admission details (never published by the Resolver).
DETAIL_DWELL_INCOMPLETE = "dwell_incomplete"
DETAIL_OBSERVATION_BEFORE_DWELL = "observation_before_dwell"
DETAIL_DETECTION_TOO_OLD = "detection_too_old"
DETAIL_FRAME_MISMATCH = "frame_mismatch"

DWELL_REASON_DETAILS = {
  DETAIL_DWELL_INCOMPLETE: REASON_INVALID_POSE,
  DETAIL_OBSERVATION_BEFORE_DWELL: REASON_INVALID_POSE,
  DETAIL_DETECTION_TOO_OLD: REASON_POSE_EXPIRED,
  DETAIL_FRAME_MISMATCH: REASON_INVALID_POSE,
}

ALL_REASON_DETAILS = {**PTZ_REASON_DETAILS, **DWELL_REASON_DETAILS}


def canonical_reason(reason_detail: str) -> str:
  """Canonical invalid_reason for a PTZ or dwell reason_detail.

  @raises KeyError for a detail outside the closed sets
  """
  return ALL_REASON_DETAILS[reason_detail]
