# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Register a reconstruction to the scene frame from paired camera poses.

A world model returns geometry and camera poses in its own frame and scale.
When the images came from a tracked device (SLAM/ARKit keyframes) we know
where each camera really was, so a similarity transform scene<-model can be
fit from the pose pairs and applied to the mesh and every returned camera.
"""

import math

import numpy as np

_RIGID_SCALE_EPS = 1e-3


def quat_xyzw_to_matrix(q):
  x, y, z, w = (float(v) for v in q)
  n = math.sqrt(x * x + y * y + z * z + w * w)
  if n < 1e-12:
    return np.eye(3)
  x, y, z, w = x / n, y / n, z / n, w / n
  return np.array([
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
  ], dtype=np.float64)


def matrix_to_quat_xyzw(R):
  m = np.asarray(R, dtype=np.float64)
  tr = m[0, 0] + m[1, 1] + m[2, 2]
  if tr > 0:
    s = math.sqrt(tr + 1.0) * 2
    w, x, y, z = 0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s
  elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
    s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
    w, x, y, z = (m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s
  elif m[1, 1] > m[2, 2]:
    s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
    w, x, y, z = (m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s
  else:
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    w, x, y, z = (m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s
  return [float(x), float(y), float(z), float(w)]


def pose_matrix(translation, quat_xyzw):
  T = np.eye(4, dtype=np.float64)
  T[:3, :3] = quat_xyzw_to_matrix(quat_xyzw)
  T[:3, 3] = np.asarray(translation, dtype=np.float64)
  return T


def _average_rotation(mats):
  """Chordal mean of rotation matrices (SVD projection of the sum)."""
  M = np.zeros((3, 3))
  for R in mats:
    M += R[:3, :3]
  U, _, Vt = np.linalg.svd(M)
  R = U @ Vt
  if np.linalg.det(R) < 0:
    U[:, -1] *= -1
    R = U @ Vt
  return R


def estimate_scene_T_model(scene_poses, model_poses):
  """Similarity transform scene<-model from paired camera-to-world 4x4 poses.

  Rotation is the mean of per-pair ``scene @ inv(model)`` (uses full camera
  orientation, so two views suffice); uniform scale is fit with that rotation
  fixed; translation closes the centroid gap.
  """
  if len(scene_poses) != len(model_poses):
    raise ValueError(f"Pose count mismatch: {len(scene_poses)} scene vs {len(model_poses)} model")
  if len(scene_poses) < 2:
    raise ValueError("Need at least 2 pose pairs for alignment")
  rels = [s @ np.linalg.inv(m) for s, m in zip(scene_poses, model_poses)]
  R = _average_rotation(rels)
  src = np.stack([p[:3, 3] for p in model_poses])
  dst = np.stack([p[:3, 3] for p in scene_poses])
  src_c = src - src.mean(axis=0)
  dst_c = dst - dst.mean(axis=0)
  rotated = src_c @ R.T
  denom = float((rotated * rotated).sum())
  scale = float((rotated * dst_c).sum() / denom) if denom > 1e-12 else 1.0
  if not math.isfinite(scale) or scale <= 0:
    scale = 1.0
  if abs(scale - 1.0) <= _RIGID_SCALE_EPS:
    scale = 1.0
  t = dst.mean(axis=0) - scale * R @ src.mean(axis=0)
  T = np.eye(4, dtype=np.float64)
  T[:3, :3] = scale * R
  T[:3, 3] = t
  return T


def apply_to_pose(scene_T_model, pose):
  """Map a camera-to-world pose through a similarity; returns (t, quat_xyzw)."""
  P = scene_T_model @ np.asarray(pose, dtype=np.float64)
  A = P[:3, :3]
  scale = float(np.cbrt(abs(np.linalg.det(A)))) or 1.0
  return P[:3, 3].tolist(), matrix_to_quat_xyzw(A / scale)


def residuals(scene_T_model, scene_poses, model_poses):
  """Per-pair camera-centre error (m) after alignment."""
  out = []
  for s, m in zip(scene_poses, model_poses):
    p = scene_T_model @ m
    out.append(float(np.linalg.norm(p[:3, 3] - s[:3, 3])))
  return out


def summary(scene_T_model):
  A = scene_T_model[:3, :3]
  scale = float(np.cbrt(abs(np.linalg.det(A)))) or 1.0
  R = A / scale
  ang = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))
  return {"scale": scale, "rotation_deg": ang,
          "translation": scene_T_model[:3, 3].tolist()}
