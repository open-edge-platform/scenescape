# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for image_transforms
Checks that the mirrored preprocessing transforms invert intrinsics exactly.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from image_transforms import mapanything_transform, vggt_transform


def _k(fx, fy, cx, cy):
  return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)


SIZES = [
  (1920, 1080),  # 16:9 landscape
  (1080, 1920),  # portrait
  (640, 480),    # 4:3
  (518, 518),    # already square
  (1281, 723),   # odd dimensions
]


class TestMapAnythingTransform:

  def test_landscape_into_batch_target_matches_vendor(self):
    """1920x1080 into a 518x392 batch: cover-scale then center crop."""
    t = mapanything_transform((1920, 1080), (518, 392))
    assert t.model_width == 518 and t.model_height == 392
    # floor(1920 * (392/1080 + 1e-8)) == 696 -> (696 - 518) // 2 == 89
    assert round(1920 * t.scale_x) == 696
    assert round(1080 * t.scale_y) == 392
    assert t.crop_left == 89
    assert t.crop_top == 0

  def test_exact_aspect_has_small_crop_only(self):
    """16:9 into the 16:9 bucket: vendor floors to 522 px so the crop is 2 px."""
    t = mapanything_transform((1920, 1080), (518, 294))
    assert t.crop_top == 0
    assert t.crop_left <= 2

  @pytest.mark.parametrize("size", SIZES)
  @pytest.mark.parametrize("target", [(518, 518), (518, 392), (518, 294), (294, 518)])
  def test_round_trip(self, size, target):
    K = _k(1100.0, 1090.0, size[0] * 0.49, size[1] * 0.52)
    t = mapanything_transform(size, target)
    K_model = t.apply_to_intrinsics(K)
    # Principal point lands inside the model image when it is near the center.
    assert 0 <= K_model[0, 2] <= t.model_width
    assert 0 <= K_model[1, 2] <= t.model_height
    np.testing.assert_allclose(t.invert_intrinsics(K_model), K, rtol=0, atol=1e-9)


class TestVGGTTransform:

  def test_landscape_shorter_side_scaled(self):
    t = vggt_transform((1920, 1080))
    assert round(1920 * t.scale_x) == 924
    assert round(1080 * t.scale_y) == 518
    assert t.crop_left == 203
    assert t.crop_top == 0

  def test_portrait_crops_vertically(self):
    t = vggt_transform((1080, 1920))
    assert t.crop_left == 0
    assert t.crop_top == 203

  @pytest.mark.parametrize("size", SIZES)
  def test_round_trip(self, size):
    K = _k(900.0, 910.0, size[0] * 0.5, size[1] * 0.5)
    t = vggt_transform(size)
    np.testing.assert_allclose(t.invert_intrinsics(t.apply_to_intrinsics(K)), K, rtol=0, atol=1e-9)

  def test_width_based_inverse_would_be_wrong(self):
    """Regression: focal inverse must follow the actual resize (924x518), not width/518."""
    t = vggt_transform((1920, 1080))
    K_model = _k(500.0, 500.0, 259.0, 259.0)
    K = t.invert_intrinsics(K_model)
    assert abs(K[0, 0] - 500.0 * 1920 / 924) < 1e-6
    assert abs(K[1, 1] - 500.0 * 1080 / 518) < 1e-6
    assert abs(K[0, 0] - 500.0 * 1920 / 518) > 100
    # Principal point recovers the crop offset on the cropped axis only.
    assert abs(K[0, 2] - (259.0 + 203) * 1920 / 924) < 1e-6
    assert abs(K[1, 2] - 259.0 * 1080 / 518) < 1e-6
