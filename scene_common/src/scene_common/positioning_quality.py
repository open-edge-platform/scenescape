# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PoseContext quality scores (diagnostic only; never replace validity gates)."""

import math


def temporal_score(sample_age_s: float, timestamp_uncertainty_s: float,
                   max_pose_age_s: float) -> float:
  """clamp(1 - (age + uncertainty) / max_pose_age_s, 0, 1)."""
  if not max_pose_age_s > 0.0:
    raise ValueError("max_pose_age_s must be > 0")
  value = 1.0 - (sample_age_s + timestamp_uncertainty_s) / max_pose_age_s
  return min(max(value, 0.0), 1.0)


def calibration_score(reprojection_rms_px: float, target_reprojection_rms_px: float) -> float:
  """exp(-0.5 * (rms / target)^2)."""
  if not target_reprojection_rms_px > 0.0:
    raise ValueError("target_reprojection_rms_px must be > 0")
  if reprojection_rms_px < 0.0:
    raise ValueError("reprojection_rms_px must be >= 0")
  return math.exp(-0.5 * (reprojection_rms_px / target_reprojection_rms_px) ** 2)


def score(temporal: float, calibration: float) -> float:
  return temporal * calibration
