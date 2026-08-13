# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Child-to-parent pose from two scenes' four-corner geospatial calibrations."""

from typing import Iterable, Optional, Sequence, Union

import numpy as np
from scipy.spatial.transform import Rotation

from scene_common.earth_lla import (
    calculateTRSLocal2LLAFromSurfacePoints,
    convertLLAToECEF,
    convertXYZToLLA,
)
from scene_common.transform import CameraPose

DEFAULT_RESIDUAL_THRESHOLD_M = 2.0
CORNER_COUNT = 4

Number = Union[int, float]
Point3 = Sequence[Number]
Corners = Sequence[Point3]


class GeospatialHierarchyError(ValueError):
  """Raised when a child-to-parent geospatial pose cannot be computed."""


def local_xyz_corners_from_extents(width_m: float, height_m: float) -> np.ndarray:
  """Axis-aligned map corners on z=0, CCW from lower-left.

  Args:
    width_m: Extent along local X in meters.
    height_m: Extent along local Y in meters.

  Returns:
    Array of shape (4, 3).
  """
  if width_m <= 0 or height_m <= 0:
    raise GeospatialHierarchyError("Local map extents must be positive")
  return np.array([
      [0.0, 0.0, 0.0],
      [width_m, 0.0, 0.0],
      [width_m, height_m, 0.0],
      [0.0, height_m, 0.0],
  ], dtype=np.float64)


def local_xyz_corners_from_image_size(
    width_px: float, height_px: float, scale_px_per_m: float) -> np.ndarray:
  """Local XYZ corners for an image map from pixel size and pixels-per-meter."""
  if scale_px_per_m is None or scale_px_per_m <= 0:
    raise GeospatialHierarchyError("Scene scale (pixels per meter) must be positive")
  if width_px <= 0 or height_px <= 0:
    raise GeospatialHierarchyError("Map image dimensions must be positive")
  return local_xyz_corners_from_extents(width_px / scale_px_per_m, height_px / scale_px_per_m)


def _as_corner_array(corners: Corners, label: str) -> np.ndarray:
  try:
    pts = np.asarray(corners, dtype=np.float64)
  except (TypeError, ValueError) as exc:
    raise GeospatialHierarchyError(f"{label} corners must be numeric") from exc
  if pts.ndim != 2 or pts.shape[1] != 3:
    raise GeospatialHierarchyError(
        f"{label} corners must be an array of [x, y, z] or [lat, lon, alt] triples")
  if pts.shape[0] != CORNER_COUNT:
    raise GeospatialHierarchyError(
        f"{label} corners must contain exactly {CORNER_COUNT} points, got {pts.shape[0]}")
  return pts


def _ecef_distance_lla(lla_a: Iterable[Number], lla_b: Iterable[Number]) -> float:
  return float(np.linalg.norm(convertLLAToECEF(lla_a) - convertLLAToECEF(lla_b)))


def _decompose_affine_to_euler(matrix: np.ndarray) -> dict:
  """Decompose a 4x4 affine into translation, XYZ Euler degrees, and scale."""
  linear = np.array(matrix[:3, :3], dtype=np.float64)
  translation = np.array(matrix[:3, 3], dtype=np.float64)
  scale = np.linalg.norm(linear, axis=0)
  if np.any(scale < 1e-12):
    raise GeospatialHierarchyError("Degenerate child-to-parent transform (zero scale)")
  rotation_matrix = linear / scale
  if np.linalg.det(rotation_matrix) < 0:
    scale[2] *= -1.0
    rotation_matrix[:, 2] *= -1.0
  try:
    euler = Rotation.from_matrix(rotation_matrix).as_euler('XYZ', degrees=True)
  except ValueError as exc:
    raise GeospatialHierarchyError("Failed to decompose child-to-parent rotation") from exc
  return {
      'translation': translation.tolist(),
      'rotation': euler.tolist(),
      'scale': scale.tolist(),
  }


def compute_child_to_parent_pose(
    parent_xyz_corners: Corners,
    parent_lla_corners: Corners,
    child_xyz_corners: Corners,
    child_lla_corners: Corners,
    residual_threshold_m: float = DEFAULT_RESIDUAL_THRESHOLD_M,
) -> dict:
  """Compute the Euler pose that maps child-local XYZ into parent-local XYZ.

  Fits each scene's local XYZ corners to its ``map_corners_lla`` via the existing
  XYZ→ECEF estimator, then composes ``inv(T_parent) @ T_child``. The affine is
  decomposed to Euler translation/rotation/scale (the ChildScene storage format).

  Args:
    parent_xyz_corners: Four parent-local surface points (z=0), CCW from lower-left.
    parent_lla_corners: Matching parent WGS84 corners [lat, lon, alt].
    child_xyz_corners: Four child-local surface points (z=0), CCW from lower-left.
    child_lla_corners: Matching child WGS84 corners [lat, lon, alt].
    residual_threshold_m: Max ECEF error after Euler reconstruction (meters).

  Returns:
    Dict with ``translation``, ``rotation`` (XYZ degrees), ``scale``,
    ``residual_m``, and reconstructed 4x4 ``matrix``.

  Raises:
    GeospatialHierarchyError: Missing/invalid corners, degenerate fit, or residual.
  """
  parent_xyz = _as_corner_array(parent_xyz_corners, "parent local")
  parent_lla = _as_corner_array(parent_lla_corners, "parent geospatial")
  child_xyz = _as_corner_array(child_xyz_corners, "child local")
  child_lla = _as_corner_array(child_lla_corners, "child geospatial")
  if residual_threshold_m <= 0:
    raise GeospatialHierarchyError("residual_threshold_m must be positive")

  try:
    parent_trs = calculateTRSLocal2LLAFromSurfacePoints(parent_xyz, parent_lla)
    child_trs = calculateTRSLocal2LLAFromSurfacePoints(child_xyz, child_lla)
  except ValueError as exc:
    raise GeospatialHierarchyError(str(exc)) from exc

  try:
    parent_inv = np.linalg.inv(parent_trs)
  except np.linalg.LinAlgError as exc:
    raise GeospatialHierarchyError("Parent geospatial transform is not invertible") from exc

  child_to_parent = parent_inv @ child_trs
  euler_pose = _decompose_affine_to_euler(child_to_parent)
  reconstructed = CameraPose(euler_pose, None)
  residual = 0.0
  for xyz, expected_lla in zip(child_xyz, child_lla):
    parent_pt = np.matmul(reconstructed.pose_mat, np.hstack([xyz, 1.0]))[:3]
    reconstructed_lla = convertXYZToLLA(parent_trs, parent_pt)
    residual = max(residual, _ecef_distance_lla(reconstructed_lla, expected_lla))

  if residual > residual_threshold_m:
    raise GeospatialHierarchyError(
        f"Geospatial child pose residual {residual:.2f} m exceeds "
        f"{residual_threshold_m:.2f} m")

  return {
      'translation': reconstructed.translation.asNumpyCartesian.tolist(),
      'rotation': reconstructed.euler_rotation.tolist(),
      'scale': list(reconstructed.scale),
      'residual_m': residual,
      'matrix': reconstructed.pose_mat.tolist(),
  }


def scene_is_georeferenced(output_lla: Optional[bool],
                           map_corners_lla: Optional[Corners]) -> bool:
  """True when a scene has geospatial output and four map corners."""
  if not output_lla or map_corners_lla is None:
    return False
  try:
    _as_corner_array(map_corners_lla, "scene geospatial")
  except GeospatialHierarchyError:
    return False
  return True
