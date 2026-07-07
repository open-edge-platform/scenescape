# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Wildtrack preprocessing helpers: constants, grid decoding, calibration parsing.

The Wildtrack dataset stores camera calibration as OpenCV ``FileStorage`` XML and
encodes ground-truth positions as indices into a flat 480x1440 grid.  This module
provides pure functions to:

- map the 7 Wildtrack camera names to canonical ``cam0``..``cam6`` ids,
- decode a ``positionID`` to a world-space (X, Y) ground point in metres,
- parse intrinsic / extrinsic calibration XML files into the canonical scene
  configuration representation (intrinsics ``[fx, fy, cx, cy]`` + distortion,
  and extrinsics ``translation`` / ``rotation`` (Euler XYZ degrees) / ``scale``).

Nothing here hard-codes the dataset location; callers pass the raw dataset path.
"""

from pathlib import Path
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

import numpy as np
import cv2
from scipy.spatial.transform import Rotation

# Wildtrack camera names in viewNum order (0..6) -> canonical cam ids.
WILDTRACK_CAMERA_NAMES: List[str] = [
  "CVLab1", "CVLab2", "CVLab3", "CVLab4", "IDIAP1", "IDIAP2", "IDIAP3",
]
NUM_CAMERAS: int = len(WILDTRACK_CAMERA_NAMES)

# Canonical camera ids exposed to the evaluation pipeline.
CAMERA_IDS: List[str] = [f"cam{i}" for i in range(NUM_CAMERAS)]

# Image resolution of the (undistorted) Wildtrack frames.
IMAGE_WIDTH: int = 1920
IMAGE_HEIGHT: int = 1080

# Ground-plane grid encoding (see dataset README / rectangles.pom header).
GRID_WIDTH: int = 480
GRID_HEIGHT: int = 1440
GRID_CELL_SIZE_M: float = 0.025
GRID_ORIGIN_X_M: float = -3.0
GRID_ORIGIN_Y_M: float = -9.0

# Wildtrack extrinsic transl(tvec) is expressed in centimetres.
CM_PER_M: float = 100.0

# Native annotation cadence: filenames are in 0.1 s units, stepped by 5 -> 2 FPS.
ANNOTATION_TIME_UNIT_S: float = 0.1
ANNOTATION_STEP: int = 5
NATIVE_FPS: float = 2.0

OBJECT_CATEGORY: str = "person"


def camera_id_for_view(view_num: int) -> str:
  """Return the canonical ``camN`` id for a Wildtrack ``viewNum`` (0..6)."""
  if not 0 <= view_num < NUM_CAMERAS:
    raise ValueError(f"Invalid Wildtrack viewNum: {view_num}")
  return CAMERA_IDS[view_num]


def decode_position_id(position_id: int) -> Tuple[float, float]:
  """Decode a Wildtrack ``positionID`` to a world ground point (X, Y) in metres.

  The grid is X-first (X varies fastest):

      grid_x = positionID mod GRID_WIDTH
      grid_y = positionID div GRID_WIDTH
      X = GRID_ORIGIN_X_M + GRID_CELL_SIZE_M * grid_x
      Y = GRID_ORIGIN_Y_M + GRID_CELL_SIZE_M * grid_y

  Args:
    position_id: Non-negative flat grid index.

  Returns:
    (X, Y) ground-plane coordinates in metres (Z is implicitly 0.0).
  """
  if position_id < 0 or position_id >= GRID_WIDTH * GRID_HEIGHT:
    raise ValueError(f"positionID out of range: {position_id}")
  grid_x = position_id % GRID_WIDTH
  grid_y = position_id // GRID_WIDTH
  x = GRID_ORIGIN_X_M + GRID_CELL_SIZE_M * grid_x
  y = GRID_ORIGIN_Y_M + GRID_CELL_SIZE_M * grid_y
  return x, y


def _read_opencv_matrix(node: ET.Element) -> np.ndarray:
  """Parse an OpenCV ``FileStorage`` matrix element into a flat float array."""
  data = node.find("data")
  if data is None or data.text is None:
    raise ValueError("Malformed OpenCV matrix: missing <data>")
  return np.array([float(v) for v in data.text.split()], dtype=np.float64)


def parse_intrinsics(xml_path: Path) -> Tuple[List[float], List[float]]:
  """Parse a Wildtrack ``intrinsic_zero`` XML file.

  Args:
    xml_path: Path to ``intr_<camera>.xml``.

  Returns:
    Tuple of ``([fx, fy, cx, cy], distortion_list)``.  For ``intrinsic_zero``
    the distortion coefficients are all zero (images are undistorted).
  """
  root = ET.parse(xml_path).getroot()
  cam_node = root.find("camera_matrix")
  if cam_node is None:
    raise ValueError(f"Missing camera_matrix in {xml_path}")
  k = _read_opencv_matrix(cam_node).reshape(3, 3)
  fx, fy = float(k[0, 0]), float(k[1, 1])
  cx, cy = float(k[0, 2]), float(k[1, 2])

  dist_node = root.find("distortion_coefficients")
  distortion = (
    _read_opencv_matrix(dist_node).tolist() if dist_node is not None else [0.0] * 5
  )
  return [fx, fy, cx, cy], distortion


def parse_extrinsics(xml_path: Path) -> Tuple[np.ndarray, np.ndarray]:
  """Parse a Wildtrack ``extrinsic`` XML file.

  Args:
    xml_path: Path to ``extr_<camera>.xml``.

  Returns:
    Tuple of ``(rvec, tvec)`` numpy arrays (world->camera, tvec in centimetres),
    each shaped (3, 1).
  """
  root = ET.parse(xml_path).getroot()
  rvec_node = root.find("rvec")
  tvec_node = root.find("tvec")
  if rvec_node is None or tvec_node is None or rvec_node.text is None or tvec_node.text is None:
    raise ValueError(f"Missing rvec/tvec in {xml_path}")
  rvec = np.array([float(v) for v in rvec_node.text.split()], dtype=np.float64).reshape(3, 1)
  tvec = np.array([float(v) for v in tvec_node.text.split()], dtype=np.float64).reshape(3, 1)
  return rvec, tvec


def extrinsics_to_pose(rvec: np.ndarray, tvec: np.ndarray) -> Dict[str, List[float]]:
  """Convert world->camera ``rvec`` / ``tvec`` (cm) to canonical camera pose.

  The canonical extrinsics describe the camera->world transform used by
  ``scene_common`` ``CameraPose``:

      R           = Rodrigues(rvec)            # world->camera rotation
      R_cw        = R^T                        # camera->world rotation
      C           = -R^T @ tvec  (cm) / 100    # camera centre in world (metres)
      rotation    = euler_XYZ(R_cw) (degrees)

  Args:
    rvec: World->camera Rodrigues rotation vector, shape (3, 1).
    tvec: World->camera translation in centimetres, shape (3, 1).

  Returns:
    Dict with ``translation`` (metres), ``rotation`` (Euler XYZ degrees),
    ``scale`` ([1, 1, 1]).
  """
  rmat, _ = cv2.Rodrigues(rvec)
  rot_cam_to_world = rmat.T
  camera_centre_cm = (-rot_cam_to_world @ tvec).flatten()
  translation_m = (camera_centre_cm / CM_PER_M).tolist()
  rotation_euler = Rotation.from_matrix(rot_cam_to_world).as_euler("XYZ", degrees=True).tolist()
  return {
    "translation": [float(v) for v in translation_m],
    "rotation": [float(v) for v in rotation_euler],
    "scale": [1.0, 1.0, 1.0],
  }


def calibration_path(dataset_path: Path, kind: str, camera_name: str) -> Path:
  """Build the path to a calibration XML file.

  Args:
    dataset_path: Root of the raw Wildtrack dataset.
    kind: ``"intrinsic_zero"`` or ``"extrinsic"``.
    camera_name: Wildtrack camera name (e.g. ``"CVLab1"``).

  Returns:
    Absolute path to the calibration XML.
  """
  prefix = "intr" if kind.startswith("intrinsic") else "extr"
  return dataset_path / "calibrations" / kind / f"{prefix}_{camera_name}.xml"
