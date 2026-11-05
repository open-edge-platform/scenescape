# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""World transforms must keep depth metadata consistent with the world ray."""

import numpy as np
import pytest

from frustum_gaussian import transform_to_world_batch
from frustum_gaussian._pure import project_frustum_batch_numpy


@pytest.mark.parametrize(
  "scale, ray",
  [
    ([2.0, 2.0, 2.0], [0.0, 0.0, 1.0]),
    ([2.0, 1.0, 0.5], [2 ** -0.5, 0.0, 2 ** -0.5]),
  ],
)
def test_pose_scale_updates_depth_metadata_and_world_point(scale, ray):
  ray = np.asarray(ray, dtype=np.float32)
  ray /= np.linalg.norm(ray)
  depth_est = 10.0
  sigma = np.eye(3, dtype=np.float32) + 4.0 * np.outer(ray, ray)
  pose = np.eye(4, dtype=np.float32)
  pose[:3, :3] = np.diag(scale)
  pose[:3, 3] = [3.0, -4.0, 2.0]
  observations = {
    "mu": (depth_est * ray)[None, :],
    "Sigma": sigma[None, :, :],
    "ray": ray[None, :],
    "depth_est": np.array([depth_est], dtype=np.float32),
    "depth_sigma": np.array([np.sqrt(5.0)], dtype=np.float32),
    "depth_lo": np.array([8.0], dtype=np.float32),
    "depth_hi": np.array([12.0], dtype=np.float32),
    "score": np.array([0.5], dtype=np.float32),
    "edge_valid": np.array([15], dtype=np.uint8),
  }

  world = transform_to_world_batch(observations, pose)
  ray_scale = np.linalg.norm(np.diag(scale) @ ray)
  reconstructed = pose[:3, 3] + world["ray"][0] * world["depth_est"][0]
  radial_variance = world["ray"][0] @ world["Sigma"][0] @ world["ray"][0]

  np.testing.assert_allclose(reconstructed, world["mu"][0], rtol=1e-6, atol=1e-6)
  assert world["depth_est"][0] == pytest.approx(depth_est * ray_scale)
  assert world["depth_lo"][0] == pytest.approx(8.0 * ray_scale)
  assert world["depth_hi"][0] == pytest.approx(12.0 * ray_scale)
  assert world["depth_sigma"][0] == pytest.approx(np.sqrt(radial_variance))
  assert world["score"][0] == observations["score"][0]
  assert world["edge_valid"][0] == observations["edge_valid"][0]


def test_numpy_backend_accepts_degenerate_box_axes_under_strict_errors():
  boxes = np.array([
    [100.0, 100.0, 100.0, 200.0],
    [100.0, 100.0, 200.0, 100.0],
  ], dtype=np.float32)
  priors = np.tile(
    np.array([0.55, 0.55, 1.70, 0.10, 0.10, 0.15], dtype=np.float32),
    (len(boxes), 1),
  )

  with np.errstate(over="raise", divide="raise", invalid="raise"):
    result = project_frustum_batch_numpy(
      boxes,
      np.array([500.0, 500.0, 200.0, 200.0], dtype=np.float32),
      np.array([400.0, 400.0], dtype=np.float32),
      priors,
    )

  assert np.all(np.isfinite(result["mu"]))
  assert np.all(np.isfinite(result["Sigma"]))
  for key in ("depth_est", "depth_sigma", "depth_lo", "depth_hi", "score"):
    assert np.all(np.isfinite(result[key])), key


def test_numpy_depth_ignores_partially_clipped_axis():
  box = np.array([[0.0, 100.0, 150.0, 300.0]], dtype=np.float32)
  prior = np.array([[3.0, 0.5, 1.5, 0.1, 0.1, 0.1]], dtype=np.float32)
  intrinsics = np.array([500.0, 500.0, 200.0, 200.0], dtype=np.float32)
  img_size = np.array([400.0, 400.0], dtype=np.float32)

  result = project_frustum_batch_numpy(box, intrinsics, img_size, prior)
  alpha_y = np.arctan((300.0 - 200.0) / 500.0) - np.arctan((100.0 - 200.0) / 500.0)
  expected_depth = 1.5 / (2.0 * np.tan(alpha_y / 2.0))
  expected_depth_lo = 1.4 / (2.0 * np.tan(alpha_y / 2.0))

  assert result["depth_est"][0] == pytest.approx(expected_depth)
  assert result["depth_lo"][0] == pytest.approx(expected_depth_lo)


def test_numpy_full_frame_box_uses_bounded_uniform_fallback():
  box = np.array([[0.0, 0.0, 400.0, 400.0]], dtype=np.float32)
  prior = np.array([[0.55, 0.55, 1.70, 0.10, 0.10, 0.15]], dtype=np.float32)
  intrinsics = np.array([500.0, 500.0, 200.0, 200.0], dtype=np.float32)
  img_size = np.array([400.0, 400.0], dtype=np.float32)

  result = project_frustum_batch_numpy(box, intrinsics, img_size, prior)
  tan_half_fov = np.tan(np.arctan(0.4))
  expected_hi = min((0.55 + 0.10) / (2.0 * tan_half_fov),
                    (1.70 + 0.15) / (2.0 * tan_half_fov))

  assert result["depth_lo"][0] == 0.0
  assert result["depth_hi"][0] == pytest.approx(expected_hi)
  assert result["depth_est"][0] == pytest.approx(max(expected_hi / 2.0, 0.1))
  assert result["depth_sigma"][0] == pytest.approx(expected_hi / np.sqrt(12.0))