# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Immutable per-frame projection context for an admitted PTZ detection.

The stored camera (home pose, intrinsics, distortion) is never modified: a
ProjectedCamera pairs the camera's static identity and intrinsics with the
`scene_from_camera` matrix of the PoseContext that admitted the detection.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

from scene_common.positioning_dwell import PoseSnapshot
from scene_common.transform import CameraPose


class ProjectedCamera:
  """Read-only camera view used wherever the Controller reads `camera.pose`."""

  def __init__(self, static_camera: Any, snapshot: PoseSnapshot):
    matrix = np.array(snapshot.payload["pose"]["matrix_4x4"], dtype=float)
    matrix.setflags(write=False)
    self.static_camera = static_camera
    self.cameraID = static_camera.cameraID
    self.ptz_calibration = getattr(static_camera, "ptz_calibration", None)
    self.pose = CameraPose(matrix, static_camera.pose.intrinsics)
    self.sequence = snapshot.sequence


@dataclass(frozen=True)
class PTZProjectionContext:
  """Everything the projection and shadow record need about the admitting pose."""
  source_id: str
  sequence: int
  calibration_version: str
  frame_id: str
  pose_timestamp_ns: int
  timestamp_uncertainty_s: float
  dwell_elapsed_s: float
  camera: ProjectedCamera
