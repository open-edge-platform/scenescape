# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Builders for PTZ PoseContext and Positioning status payloads used by tests."""

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from scene_common import positioning_reasons as reasons

IDENTITY_MATRIX = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 4], [0, 0, 0, 1]]
DEFAULT_VALIDITY_S = 0.5
DEFAULT_UNCERTAINTY_S = 0.01


def iso(moment: datetime) -> str:
  return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def pose_context(source_id: str, sequence: int, timestamp: datetime, frame_id: str,
                 calibration_version: str, matrix: Optional[List[List[float]]] = None,
                 valid: bool = True, motion_state: str = "stationary",
                 uncertainty_s: float = DEFAULT_UNCERTAINTY_S,
                 validity_s: float = DEFAULT_VALIDITY_S,
                 reason_detail: str = reasons.DETAIL_MOVING) -> Dict[str, Any]:
  """PoseContext payload; an invalid one carries `reason_detail` and no pose."""
  payload = {
    "schema_version": 1,
    "source_id": source_id,
    "timestamp": iso(timestamp),
    "valid_until": iso(timestamp + timedelta(seconds=validity_s)),
    "sequence": sequence,
    "valid": valid,
    "motion_state": motion_state,
    "sample_age_s": 0.0,
    "timestamp_uncertainty_s": uncertainty_s,
    "calibration_version": calibration_version,
  }
  if valid:
    payload["pose"] = {
      "frame_id": frame_id,
      "transform_direction": "scene_from_camera",
      "matrix_layout": "row_major",
      "matrix_4x4": matrix or IDENTITY_MATRIX,
      "translation_unit": "m",
    }
    payload["quality"] = {"score": 1.0, "temporal_score": 1.0, "calibration_score": 1.0,
                          "reprojection_rms_px": 0.5}
  else:
    payload["invalid_reason"] = reasons.canonical_reason(reason_detail)
    payload["reason_detail"] = reason_detail
  return payload


def status_payload(resolver_id: str, session_start: datetime,
                   state: str = "online") -> Dict[str, Any]:
  return {"resolver_id": resolver_id, "status": state, "timestamp": iso(session_start)}


def rotated_matrix(base: List[List[float]], yaw_deg: float) -> List[List[float]]:
  """`base` (scene_from_camera) rotated by `yaw_deg` about the scene Z axis, same translation."""
  angle = math.radians(yaw_deg)
  cos, sin = math.cos(angle), math.sin(angle)
  rotation = [[cos, -sin, 0.0], [sin, cos, 0.0], [0.0, 0.0, 1.0]]
  matrix = [[0.0] * 4 for _ in range(4)]
  for row in range(3):
    for col in range(3):
      matrix[row][col] = sum(rotation[row][k] * base[k][col] for k in range(3))
    matrix[row][3] = base[row][3]
  matrix[3] = [0.0, 0.0, 0.0, 1.0]
  return matrix
