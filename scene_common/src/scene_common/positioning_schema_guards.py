# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PoseContext guards that JSON Schema cannot express.

Run after schema validation and before any use of the pose: bounded payload
size, finite numbers, and a rigid row-major 4x4 matrix with unit scale.
"""

import math
from typing import Any, Mapping, Union

import numpy as np

MAX_POSE_CONTEXT_BYTES = 4096
RIGID_TOLERANCE = 1e-6

_FINITE_SCALARS = ("sample_age_s", "timestamp_uncertainty_s")
_QUALITY_FIELDS = ("score", "temporal_score", "calibration_score", "reprojection_rms_px")


class PoseContextGuardError(ValueError):
  """Raised when a PoseContext payload fails a guard; the pose must not be used."""


def check_payload_size(raw: Union[bytes, str]) -> None:
  size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
  if size > MAX_POSE_CONTEXT_BYTES:
    raise PoseContextGuardError(
      f"PoseContext payload is {size} bytes (limit {MAX_POSE_CONTEXT_BYTES})")


def validate_pose_context_payload(payload: Mapping[str, Any]) -> None:
  """@raises PoseContextGuardError when any guard fails"""
  if not isinstance(payload, Mapping):
    raise PoseContextGuardError("PoseContext must be an object")
  for key in _FINITE_SCALARS:
    if key in payload:
      _finite(payload[key], key)
  quality = payload.get("quality")
  if isinstance(quality, Mapping):
    for key in _QUALITY_FIELDS:
      if key in quality:
        _finite(quality[key], f"quality.{key}")
  if payload.get("valid") is True:
    pose = payload.get("pose")
    if not isinstance(pose, Mapping):
      raise PoseContextGuardError("valid PoseContext requires a pose object")
    _check_rigid_matrix(pose.get("matrix_4x4"))


def _check_rigid_matrix(rows) -> None:
  if not isinstance(rows, (list, tuple)) or len(rows) != 4:
    raise PoseContextGuardError("matrix_4x4 must have exactly 4 rows")
  for row in rows:
    if not isinstance(row, (list, tuple)) or len(row) != 4:
      raise PoseContextGuardError("matrix_4x4 rows must have exactly 4 values")
    for value in row:
      _finite(value, "matrix_4x4")
  matrix = np.asarray(rows, dtype=float)
  if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=RIGID_TOLERANCE, rtol=0.0):
    raise PoseContextGuardError("matrix_4x4 last row must be [0, 0, 0, 1]")
  rotation = matrix[:3, :3]
  if not np.allclose(rotation @ rotation.T, np.eye(3), atol=RIGID_TOLERANCE, rtol=0.0):
    raise PoseContextGuardError("matrix_4x4 rotation block must be orthonormal (unit scale)")
  if np.linalg.det(rotation) <= 0.0:
    raise PoseContextGuardError("matrix_4x4 rotation block must be a proper rotation")


def _finite(value, label: str) -> float:
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
    raise PoseContextGuardError(f"{label} must be a finite number")
  return float(value)
