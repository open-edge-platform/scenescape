# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hybrid scene view: the GLB top view pasted over the flat base map."""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from manager import glb_composite
from manager.glb_composite import compositeGlbOverBaseMap, hybridThumbnail, isHybridView
from scene_common.earth_lla import localFootprintCornersLLA

GRAY = 100
RED = [255, 0, 0]


def _base(height, width):
  return np.full((height, width, 3), GRAY, dtype=np.uint8)


def _glb(height, width):
  return np.full((height, width, 3), RED, dtype=np.uint8)


def test_glb_is_pasted_at_bottom_left_offset_in_image_rows():
  """Positive: a 2x2 GLB at (3 m, 2 m) on a 10-px-tall base lands in rows 6-7, cols 3-4."""
  base = _base(10, 20)
  mask = np.ones((2, 2), dtype=bool)
  out = compositeGlbOverBaseMap(base, _glb(2, 2), mask, 1.0, 1.0, [3.0, 2.0])
  painted = np.all(out == RED, axis=2)
  assert painted.sum() == 4
  assert painted[6:8, 3:5].all()


def test_pixels_outside_the_glb_mask_keep_the_base_map():
  """Negative: where the mask is False the base map shows through."""
  base = _base(4, 4)
  mask = np.array([[True, False], [False, True]])
  out = compositeGlbOverBaseMap(base, _glb(2, 2), mask, 1.0, 1.0, [0.0, 2.0])
  # top = 4 - 2 - 2 = 0 -> GLB covers rows 0-1, cols 0-1
  assert np.array_equal(out[0, 0], RED)
  assert np.array_equal(out[0, 1], [GRAY] * 3)
  assert np.array_equal(out[1, 0], [GRAY] * 3)
  assert np.array_equal(out[1, 1], RED)
  assert np.array_equal(out[2:, :], base[2:, :])


def test_glb_partly_outside_the_base_is_clipped():
  """Edge: a GLB hanging off the left and bottom edges paints only the visible pixels."""
  base = _base(4, 4)
  out = compositeGlbOverBaseMap(base, _glb(2, 2), np.ones((2, 2), dtype=bool),
                                1.0, 1.0, [-1.0, -1.0])
  # left = -1, top = 4 + 1 - 2 = 3 -> only pixel (3, 0) is inside
  expected = base.copy()
  expected[3, 0] = RED
  assert np.array_equal(out, expected)


def test_glb_fully_outside_the_base_returns_an_unchanged_copy():
  """Edge: no overlap returns the base map unchanged, as a new array."""
  base = _base(4, 4)
  out = compositeGlbOverBaseMap(base, _glb(2, 2), np.ones((2, 2), dtype=bool),
                                1.0, 1.0, [50.0, 50.0])
  assert np.array_equal(out, base)
  assert out is not base


def test_glb_is_resized_to_the_base_scale():
  """Positive: GLB at 1 px/m on a base at 2 px/m is drawn twice as large."""
  base = _base(8, 8)
  out = compositeGlbOverBaseMap(base, _glb(2, 2), np.ones((2, 2), dtype=bool),
                                1.0, 2.0, [0.0, 0.0])
  # 2x2 m GLB -> 4x4 px, bottom-left at row 8 - 4 = 4
  assert np.all(out[4:8, 0:4] == RED)
  assert np.all(out[0:4, :] == GRAY)
  assert np.all(out[4:8, 4:] == GRAY)


@pytest.mark.parametrize("scene", [
  SimpleNamespace(use_glb_map=False, base_map='b.png', base_scale=10.0,
                  base_map_corners_lla=[[1, 1, 0]], map_corners_lla=[[1, 1, 0]]),
  SimpleNamespace(use_glb_map=True, base_map=None, base_scale=10.0,
                  base_map_corners_lla=[[1, 1, 0]], map_corners_lla=[[1, 1, 0]]),
  SimpleNamespace(use_glb_map=True, base_map='b.png', base_scale=None,
                  base_map_corners_lla=[[1, 1, 0]], map_corners_lla=[[1, 1, 0]]),
  SimpleNamespace(use_glb_map=True, base_map='b.png', base_scale=10.0,
                  base_map_corners_lla=None, map_corners_lla=[[1, 1, 0]]),
])
def test_is_hybrid_view_requires_a_glb_on_a_base_map(scene):
  """Negative: a scene missing any of the hybrid inputs is not hybrid."""
  assert isHybridView(scene) is False


def test_is_hybrid_view_true_when_all_inputs_present():
  """Positive: an applied GLB over a base map with scale and corners is hybrid."""
  scene = SimpleNamespace(use_glb_map=True, base_map='b.png', base_scale=10.0,
                          base_map_corners_lla=[[1, 1, 0]], map_corners_lla=[[1, 1, 0]])
  assert isHybridView(scene) is True


def test_hybrid_thumbnail_is_drawn_at_the_base_scale(tmp_path):
  """Positive: the hybrid thumbnail matches the base map grid and reports its scale."""
  base_path = tmp_path / 'base.png'
  Image.fromarray(_base(20, 30)).save(base_path)
  base_map = SimpleNamespace(name='base.png',
                             storage=SimpleNamespace(open=lambda name, mode: open(base_path, mode)))
  base_corners = localFootprintCornersLLA(center_lat=52.0, center_lng=21.0, heading_deg=0.0,
                                          width_m=30.0, height_m=20.0).tolist()
  scene = SimpleNamespace(use_glb_map=True, base_map=base_map, base_scale=12.0,
                          base_map_corners_lla=base_corners,
                          map_corners_lla=[base_corners[0]] * 4,
                          map=SimpleNamespace(path='raw.glb'))
  glb_img = _glb(5, 7)
  with patch.object(glb_composite, 'generateOrthoViewWithMask',
                    return_value=(glb_img, 4.0, np.ones((5, 7), dtype=bool))):
    img, scale = hybridThumbnail(scene)
  assert scale == 12.0
  assert img.shape == (20, 30, 3)
  assert np.any(np.all(img == RED, axis=2))
