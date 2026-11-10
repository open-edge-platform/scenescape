# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from scenescape-v2-architecture/algorithms/frustum-gaussian.
# See NOTICE in this package for provenance requirements.

"""Gaussian frustum projection for multi-camera 3D tracking.

Prefers the native C++/TBB kernel (``_frustum_gaussian_cpp``, built from
``cpp/`` via scikit-build-core); falls back to the pure-numpy kernel when the
extension is unavailable (e.g. a source checkout without a built wheel).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ._pure import (
  EDGE_ALL,
  EDGE_BOTTOM,
  EDGE_LEFT,
  EDGE_RIGHT,
  EDGE_TOP,
  project_frustum_batch_numpy,
)

try:
  from . import _frustum_gaussian_cpp as _cpp
except ImportError:
  _cpp = None

__version__ = "0.1.0"

__all__ = [
  "EDGE_LEFT", "EDGE_RIGHT", "EDGE_TOP", "EDGE_BOTTOM", "EDGE_ALL",
  "PERSON_SHAPE_PRIOR",
  "project_frustum_batch",
  "transform_to_world_batch",
  "from_scenescape_detections",
  "to_scenescape_format",
]

# Pedestrian prior from ALGORITHM.md typical scene-class table.
PERSON_SHAPE_PRIOR = {
  "mu_x": 0.55,
  "mu_y": 0.55,
  "mu_z": 1.70,
  "sigma_x": 0.10,
  "sigma_y": 0.10,
  "sigma_z": 0.15,
}


def project_frustum_batch(
  detections_or_dict: dict[str, np.ndarray] | None = None,
  intrinsics: np.ndarray | None = None,
  img_size: np.ndarray | None = None,
  *,
  boxes: np.ndarray | None = None,
  priors: np.ndarray | None = None,
  sigma_px: float = 2.0,
  clipped: np.ndarray | None = None,
  axis_aware: bool | np.ndarray = True,
  **kwargs: Any,
) -> dict[str, np.ndarray]:
  """Project a batch of 2D boxes to ray-elongated Gaussians (camera frame).

  ``axis_aware`` (bool or per-detection mask): when True, BB width maps to
  ``mu_x`` and height to ``mu_z``; when False, use orientation-averaged size.
  """
  inputs = _resolve_batch_inputs(
    detections_or_dict, boxes, priors, intrinsics, img_size, clipped, axis_aware)
  sensor = kwargs.get("sensor")
  if _cpp is None:
    return _project_batch_numpy(inputs, sigma_px, sensor)
  return _project_batch_native(inputs, sigma_px, sensor)


def _resolve_batch_inputs(
    detections_or_dict, boxes, priors, intrinsics, img_size, clipped, axis_aware):
  ranges = None
  if isinstance(detections_or_dict, dict):
    ranges = detections_or_dict.get("ranges")
    if "boxes" in detections_or_dict:
      boxes = detections_or_dict["boxes"]
      priors = detections_or_dict["priors"]
      clipped = detections_or_dict.get("clipped", clipped)
      axis_aware = detections_or_dict.get("axis_aware", axis_aware)
  if boxes is None or priors is None or intrinsics is None or img_size is None:
    raise TypeError(
      "project_frustum_batch requires boxes, priors, intrinsics, and img_size")
  return (
    np.asarray(boxes, dtype=np.float32),
    np.asarray(priors, dtype=np.float32),
    np.asarray(intrinsics, dtype=np.float32),
    np.asarray(img_size, dtype=np.float32),
    None if clipped is None else np.asarray(clipped, dtype=np.uint8),
    axis_aware,
    ranges,
  )


def _project_batch_numpy(inputs, sigma_px, sensor):
  boxes, priors, intrinsics, img_size, clipped, axis_aware, ranges = inputs
  if ranges is not None or sensor is not None:
    raise NotImplementedError("range fusion requires the native frustum kernel")
  return project_frustum_batch_numpy(
    boxes=boxes,
    intrinsics=intrinsics,
    img_size=img_size,
    priors=priors,
    sigma_px=float(sigma_px),
    clipped=clipped,
    axis_aware=axis_aware,
  )


def _project_batch_native(inputs, sigma_px, sensor):
  boxes, priors, intrinsics, img_size, clipped, axis_aware, ranges = inputs
  observations: dict[str, np.ndarray] = {"boxes": boxes, "priors": priors}
  if ranges is not None:
    ranges = np.asarray(ranges, dtype=np.float32)
    if ranges.shape != (boxes.shape[0],):
      raise ValueError("ranges must have shape (N,)")
    observations["ranges"] = ranges
  if clipped is not None:
    observations["clipped"] = clipped
  if not (isinstance(axis_aware, (bool, np.bool_)) and bool(axis_aware)):
    observations["axis_aware"] = np.broadcast_to(
      np.asarray(axis_aware, dtype=np.uint8), (boxes.shape[0],)).copy()
  return _cpp.project_frustum_batch(
    observations, intrinsics, img_size, sigma_px=float(sigma_px), sensor=sensor)


def transform_to_world_batch(
  obs_dict: dict[str, np.ndarray],
  pose_mat: np.ndarray,
) -> dict[str, np.ndarray]:
  """Transform camera-frame batch Gaussians to world frame.

  ``pose_mat`` is camera→world 4×4 (row-major), matching SceneScape CameraPose.
  """
  pm = np.asarray(pose_mat, dtype=np.float32)
  if pm.shape != (4, 4):
    raise ValueError(f"pose_mat must be (4,4), got {pm.shape}")

  rot = pm[:3, :3]
  translation = pm[:3, 3]
  mu = np.asarray(obs_dict["mu"], dtype=np.float32)
  sigma = np.asarray(obs_dict["Sigma"], dtype=np.float32)
  ray = np.asarray(obs_dict["ray"], dtype=np.float32)

  mu_w = (mu @ rot.T) + translation
  sigma_w = np.einsum("ij,njk,lk->nil", rot, sigma, rot)
  ray_w = ray @ rot.T
  ray_scale = np.linalg.norm(ray_w, axis=1)
  ray_w = ray_w / np.maximum(ray_scale[:, None], 1e-12)
  depth_variance_w = np.einsum("ni,nij,nj->n", ray_w, sigma_w, ray_w)

  out = dict(obs_dict)
  out["mu"] = mu_w.astype(np.float32)
  out["Sigma"] = sigma_w.astype(np.float32)
  out["ray"] = ray_w.astype(np.float32)
  out["depth_est"] = (np.asarray(obs_dict["depth_est"], dtype=np.float32)
                      * ray_scale).astype(np.float32)
  out["depth_sigma"] = np.sqrt(np.maximum(depth_variance_w, 0.0)).astype(np.float32)
  out["depth_lo"] = (np.asarray(obs_dict["depth_lo"], dtype=np.float32)
                     * ray_scale).astype(np.float32)
  out["depth_hi"] = (np.asarray(obs_dict["depth_hi"], dtype=np.float32)
                     * ray_scale).astype(np.float32)
  return out


def from_scenescape_detections(
  detections: list[dict[str, Any]],
  intrinsics: dict[str, float],
  shape_prior: dict[str, float] | None = None,
  *,
  sigma_px: float = 2.0,
  axis_aware: bool | np.ndarray = True,
) -> dict[str, np.ndarray]:
  """Convert SceneScape detection dicts to a batch frustum result (camera frame).

  ``axis_aware`` may be a single bool or a length-N mask (or per-detection
  ``axis_aware`` / ``axis_aware_sizing`` keys on each detection dict).
  """
  count = len(detections)
  if count == 0:
    return {
      "mu": np.empty((0, 3), np.float32),
      "Sigma": np.empty((0, 3, 3), np.float32),
      "ray": np.empty((0, 3), np.float32),
      "depth_est": np.empty(0, np.float32),
      "depth_sigma": np.empty(0, np.float32),
      "depth_lo": np.empty(0, np.float32),
      "depth_hi": np.empty(0, np.float32),
      "score": np.empty(0, np.float32),
      "edge_valid": np.empty(0, np.uint8),
    }

  boxes = np.empty((count, 4), dtype=np.float32)
  per_det_aa = []
  for i, det in enumerate(detections):
    bb = det["bounding_box_px"]
    if isinstance(bb, dict):
      x = float(bb["x"])
      y = float(bb["y"])
      width = float(bb["width"])
      height = float(bb["height"])
    else:
      x, y, width, height = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
    boxes[i] = [x, y, x + width, y + height]
    if "axis_aware" in det:
      per_det_aa.append(bool(det["axis_aware"]))
    elif "axis_aware_sizing" in det:
      per_det_aa.append(bool(det["axis_aware_sizing"]))

  if len(per_det_aa) == count:
    axis_aware = np.asarray(per_det_aa, dtype=bool)

  intr = np.array(
    [intrinsics["fx"], intrinsics["fy"], intrinsics["cx"], intrinsics["cy"]],
    dtype=np.float32,
  )
  img_sz = np.array(
    [intrinsics["width"], intrinsics["height"]],
    dtype=np.float32,
  )

  prior = shape_prior if shape_prior is not None else PERSON_SHAPE_PRIOR
  row = [
    prior.get("mu_x", 0.55),
    prior.get("mu_y", 0.55),
    prior.get("mu_z", 1.70),
    prior.get("sigma_x", 0.0),
    prior.get("sigma_y", 0.0),
    prior.get("sigma_z", 0.0),
  ]
  priors = np.tile(row, (count, 1)).astype(np.float32)

  return project_frustum_batch(
    {"boxes": boxes, "priors": priors},
    intr, img_sz,
    sigma_px=sigma_px,
    axis_aware=axis_aware,
  )


def to_scenescape_format(
  obs_dict: dict[str, np.ndarray],
  pose_mat: np.ndarray,
) -> dict[str, np.ndarray]:
  """Transform a batch frustum result from camera frame to world frame."""
  return transform_to_world_batch(obs_dict, pose_mat)
