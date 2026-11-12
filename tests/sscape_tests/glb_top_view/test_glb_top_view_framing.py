# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Preview framing for GLB top views.

The preview frames the mesh from its own min corner and keeps the image aspect
equal to the footprint, because the overlay stretches the image onto it. The
stored translation places the map in the scene and must not move the image.
"""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import open3d as o3d
import pytest

from scene_common.glb_top_view import (
  THUMBNAIL_RESOLUTION,
  generateOrthoView,
  thumbnailResolution,
)


def _box(size, origin):
  legacy = o3d.geometry.TriangleMesh.create_box(*size)
  legacy.translate(origin)
  return o3d.t.geometry.TriangleMesh.from_legacy(legacy)


def _scene(translation_x=0.0, translation_y=0.0):
  return SimpleNamespace(
    rotation_x=0.0,
    rotation_y=0.0,
    rotation_z=0.0,
    translation_x=translation_x,
    translation_y=translation_y,
  )


class TestThumbnailResolution:

  @pytest.mark.parametrize("size,expected", [
    ((10.0, 4.0, 1.0), (1024, 410)),
    ((4.0, 10.0, 1.0), (307, 768)),
    ((10.0, 10.0, 1.0), (768, 768)),
    ((0.5, 0.25, 1.0), (1024, 512)),
  ])
  def test_fits_thumbnail_cap_and_keeps_aspect(self, size, expected):
    res_x, res_y = thumbnailResolution(np.array(size))
    assert (res_x, res_y) == expected
    assert res_x <= THUMBNAIL_RESOLUTION['x']
    assert res_y <= THUMBNAIL_RESOLUTION['y']
    assert res_x / res_y == pytest.approx(size[0] / size[1], rel=5e-3)


class TestGenerateOrthoViewFraming:

  @pytest.mark.parametrize("origin", [
    [0.0, 0.0, 0.0],
    [5.0, -3.0, 2.0],
    [-5.0, -2.0, -0.5],
  ])
  @pytest.mark.parametrize("translation", [(0.0, 0.0), (123.0, -45.0)])
  @patch("scene_common.glb_top_view.renderTopView")
  @patch("scene_common.glb_top_view.extractMeshFromGLB")
  def test_frames_mesh_from_min_corner_ignoring_translation(
      self, mock_extract, mock_render, origin, translation):
    mock_extract.return_value = (_box((10.0, 4.0, 1.0), origin), [])
    mock_render.return_value = (np.zeros((410, 1024, 3), dtype=np.uint8), 102.4)

    img, _ = generateOrthoView(_scene(*translation), "scene.glb")

    triangle_mesh, _, glb_size, res_x, res_y = mock_render.call_args.args
    min_bound = triangle_mesh.get_axis_aligned_bounding_box().min_bound.numpy()
    np.testing.assert_allclose(min_bound, [0.0, 0.0, 0.0], atol=1e-5)
    np.testing.assert_allclose(glb_size, [10.0, 4.0, 1.0], atol=1e-5)
    assert (res_x, res_y) == (1024, 410)
    assert img.shape == (410, 1024, 3)

  @patch("scene_common.glb_top_view.renderTopView")
  @patch("scene_common.glb_top_view.extractMeshFromGLB")
  def test_square_footprint_uses_square_thumbnail(self, mock_extract, mock_render):
    mock_extract.return_value = (_box((10.0, 10.0, 1.0), [3.0, 3.0, 0.0]), [])
    mock_render.return_value = (np.zeros((768, 768, 3), dtype=np.uint8), 76.8)

    generateOrthoView(_scene(), "scene.glb")

    assert mock_render.call_args.args[3:5] == (768, 768)
