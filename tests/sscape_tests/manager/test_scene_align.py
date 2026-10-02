# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Similarity registration of a reconstruction to known camera poses."""

import math

import numpy as np
import pytest

from manager import scene_align as sa


def _rand_pose(rng):
  q = rng.normal(size=4); q /= np.linalg.norm(q)
  return sa.pose_matrix(rng.uniform(-3, 3, 3), q)


@pytest.mark.parametrize("scale", [1.0, 0.5, 2.7])
def test_recovers_known_similarity(scale):
  rng = np.random.default_rng(7)
  scene_poses = [_rand_pose(rng) for _ in range(8)]
  # model = inverse similarity of scene: model_pose = S^-1 @ scene_pose
  q = rng.normal(size=4); q /= np.linalg.norm(q)
  R = sa.quat_xyzw_to_matrix(q)
  S = np.eye(4); S[:3, :3] = scale * R; S[:3, 3] = [1.0, -2.0, 0.5]
  S_inv = np.linalg.inv(S)
  model_poses = []
  for P in scene_poses:
    M = S_inv @ P
    # strip the scale from the rotation block so it is a valid pose
    A = M[:3, :3]; s = np.cbrt(abs(np.linalg.det(A)))
    M[:3, :3] = A / s
    model_poses.append(M)

  T = sa.estimate_scene_T_model(scene_poses, model_poses)
  res = sa.residuals(T, scene_poses, model_poses)
  summ = sa.summary(T)
  assert abs(summ["scale"] - scale) < 1e-6
  assert max(res) < 1e-6
  # orientations map correctly too
  for P, M in zip(scene_poses, model_poses):
    _, qq = sa.apply_to_pose(T, M)
    assert np.allclose(sa.quat_xyzw_to_matrix(qq), P[:3, :3], atol=1e-6)


def test_two_pairs_suffice_and_one_does_not():
  rng = np.random.default_rng(1)
  a, b = _rand_pose(rng), _rand_pose(rng)
  T = sa.estimate_scene_T_model([a, b], [a, b])
  assert np.allclose(T, np.eye(4), atol=1e-9)
  with pytest.raises(ValueError):
    sa.estimate_scene_T_model([a], [a])


def test_quaternion_round_trip():
  rng = np.random.default_rng(3)
  for _ in range(20):
    q = rng.normal(size=4); q /= np.linalg.norm(q)
    R = sa.quat_xyzw_to_matrix(q)
    q2 = sa.matrix_to_quat_xyzw(R)
    assert np.allclose(sa.quat_xyzw_to_matrix(q2), R, atol=1e-9)
