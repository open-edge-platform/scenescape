# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for GLB thumbnail texture capping in renderTopView.

The manager thumbnail path crashes natively when Open3D uploads very large
texture maps (e.g. 32768x2048). renderTopView must downscale for the preview
only, preserve aspect ratio, and leave the source texture maps unchanged.

Import path: scene_common is available via tests/conftest.py / package install;
no per-file sys.path inserts.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import open3d as o3d
import pytest

from scene_common.glb_top_view import (
  MAX_THUMBNAIL_TEXTURE_SIZE,
  materialToMaterialRecord,
  renderTopView,
)

# Wide atlas mirrors the multi-mesh GLB that triggered the crash; tall covers
# the rows > columns orientation of the same longest-side cap.
_WIDE_COLUMNS = 8192
_WIDE_ROWS = 2048
_TALL_COLUMNS = 2048
_TALL_ROWS = 8192
_UNDER_CAP_COLUMNS = 2048
_UNDER_CAP_ROWS = 1024


def _texture_image(columns, rows):
  """Build a tensor Image with the given width (columns) and height (rows)."""
  return o3d.t.geometry.Image(np.zeros((rows, columns, 3), dtype=np.uint8))


def _tensor_mesh_with_textures(texture_maps):
  material = SimpleNamespace(
    vector_properties={},
    scalar_properties={},
    texture_maps=texture_maps,
  )
  return SimpleNamespace(material=material)


def _tensor_mesh_with_albedo(albedo_img):
  return _tensor_mesh_with_textures({"albedo": albedo_img})


def _mock_offscreen_renderer():
  renderer = MagicMock()
  renderer.render_to_image.return_value = MagicMock(name="rendered_image")
  return renderer


def _legacy_shape(legacy_img):
  arr = np.asarray(legacy_img)
  # Open3D legacy Image is (rows, columns[, channels])
  return arr.shape[1], arr.shape[0]


def _assert_capped_aspect(capped_cols, capped_rows, columns, rows):
  longest = max(columns, rows)
  expected_scale = MAX_THUMBNAIL_TEXTURE_SIZE / longest
  assert max(capped_cols, capped_rows) == MAX_THUMBNAIL_TEXTURE_SIZE
  assert capped_cols == pytest.approx(columns * expected_scale, abs=1)
  assert capped_rows == pytest.approx(rows * expected_scale, abs=1)
  assert capped_cols / capped_rows == pytest.approx(columns / rows)


@pytest.mark.parametrize("columns,rows", [
  (_WIDE_COLUMNS, _WIDE_ROWS),
  (_TALL_COLUMNS, _TALL_ROWS),
])
@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_caps_oversized_texture_preserves_aspect(
    mock_renderer_cls, columns, rows):
  """Oversized albedo is capped on the long side with aspect preserved."""
  mock_renderer_cls.return_value = _mock_offscreen_renderer()
  source = _texture_image(columns, rows)
  tensor_mesh = [_tensor_mesh_with_albedo(source)]
  triangle_mesh = MagicMock(name="triangle_mesh")
  glb_size = np.array([10.0, 8.0, 3.0])

  renderTopView(triangle_mesh, tensor_mesh, glb_size, 1024, 768)

  mat_record = mock_renderer_cls.return_value.scene.add_geometry.call_args.args[2]
  capped_cols, capped_rows = _legacy_shape(mat_record.albedo_img)
  _assert_capped_aspect(capped_cols, capped_rows, columns, rows)


@pytest.mark.parametrize("map_key,attr", [
  ("albedo", "albedo_img"),
  ("normal", "normal_img"),
  ("ao_rough_metal", "ao_rough_metal_img"),
])
@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_caps_each_handled_texture_key(
    mock_renderer_cls, map_key, attr):
  """albedo, normal, and ao_rough_metal each receive the longest-side cap."""
  mock_renderer_cls.return_value = _mock_offscreen_renderer()
  source = _texture_image(_WIDE_COLUMNS, _WIDE_ROWS)
  tensor_mesh = [_tensor_mesh_with_textures({map_key: source})]

  renderTopView(MagicMock(), tensor_mesh, np.array([10.0, 8.0, 3.0]), 1024, 768)

  mat_record = mock_renderer_cls.return_value.scene.add_geometry.call_args.args[2]
  capped_cols, capped_rows = _legacy_shape(getattr(mat_record, attr))
  _assert_capped_aspect(capped_cols, capped_rows, _WIDE_COLUMNS, _WIDE_ROWS)


@pytest.mark.parametrize("columns,rows", [
  (_WIDE_COLUMNS, _WIDE_ROWS),
  (_TALL_COLUMNS, _TALL_ROWS),
])
@patch("scene_common.glb_top_view.rendering.MaterialRecord")
@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_resize_scale_uses_longest_side(
    mock_renderer_cls, mock_mat_record_cls, columns, rows):
  """Mocked atlas verifies the uniform scale is 4096 / longest_side."""
  mock_renderer_cls.return_value = _mock_offscreen_renderer()
  mat_record = MagicMock(name="mat_record")
  mock_mat_record_cls.return_value = mat_record

  resized = MagicMock(name="resized_texture")
  resized.to_legacy.return_value = MagicMock(name="legacy_resized")
  source = MagicMock(name="oversized_texture")
  source.columns = columns
  source.rows = rows
  source.resize.return_value = resized

  tensor_mesh = [_tensor_mesh_with_albedo(source)]
  renderTopView(MagicMock(), tensor_mesh, np.array([10.0, 8.0, 3.0]), 1024, 768)

  expected_scale = MAX_THUMBNAIL_TEXTURE_SIZE / max(columns, rows)
  source.resize.assert_called_once_with(
    expected_scale, o3d.t.geometry.InterpType.Linear)
  assert mat_record.albedo_img is resized.to_legacy.return_value
  assert tensor_mesh[0].material.texture_maps["albedo"] is source


@patch("scene_common.glb_top_view.rendering.MaterialRecord")
@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_skips_unused_texture_maps(
    mock_renderer_cls, mock_mat_record_cls):
  """Unused texture_maps keys are not downscaled for the thumbnail."""
  mock_renderer_cls.return_value = _mock_offscreen_renderer()
  mock_mat_record_cls.return_value = MagicMock(name="mat_record")

  unused = MagicMock(name="unused_texture")
  unused.columns = _WIDE_COLUMNS
  unused.rows = _WIDE_ROWS
  albedo = MagicMock(name="albedo_texture")
  albedo.columns = _UNDER_CAP_COLUMNS
  albedo.rows = _UNDER_CAP_ROWS
  albedo.to_legacy.return_value = MagicMock(name="legacy_albedo")

  tensor_mesh = [_tensor_mesh_with_textures({
    "albedo": albedo,
    "emissive": unused,
  })]
  renderTopView(MagicMock(), tensor_mesh, np.array([10.0, 8.0, 3.0]), 1024, 768)

  unused.resize.assert_not_called()
  unused.to_legacy.assert_not_called()
  albedo.resize.assert_not_called()
  albedo.to_legacy.assert_called_once_with()


@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_does_not_mutate_source_texture(mock_renderer_cls):
  """Resize is preview-only; the material texture map keeps original dimensions."""
  mock_renderer_cls.return_value = _mock_offscreen_renderer()
  source = _texture_image(_WIDE_COLUMNS, _WIDE_ROWS)
  tensor_mesh = [_tensor_mesh_with_albedo(source)]
  triangle_mesh = MagicMock(name="triangle_mesh")
  glb_size = np.array([10.0, 8.0, 3.0])

  renderTopView(triangle_mesh, tensor_mesh, glb_size, 1024, 768)

  kept = tensor_mesh[0].material.texture_maps["albedo"]
  assert kept.columns == _WIDE_COLUMNS
  assert kept.rows == _WIDE_ROWS
  assert kept is source


@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_skips_resize_when_under_cap(mock_renderer_cls):
  """Textures already within the cap keep their original dimensions."""
  mock_renderer_cls.return_value = _mock_offscreen_renderer()
  source = _texture_image(_UNDER_CAP_COLUMNS, _UNDER_CAP_ROWS)
  tensor_mesh = [_tensor_mesh_with_albedo(source)]
  triangle_mesh = MagicMock(name="triangle_mesh")
  glb_size = np.array([10.0, 8.0, 3.0])

  renderTopView(triangle_mesh, tensor_mesh, glb_size, 1024, 768)

  mat_record = mock_renderer_cls.return_value.scene.add_geometry.call_args.args[2]
  out_cols, out_rows = _legacy_shape(mat_record.albedo_img)
  assert (out_cols, out_rows) == (_UNDER_CAP_COLUMNS, _UNDER_CAP_ROWS)
  assert source.columns == _UNDER_CAP_COLUMNS
  assert source.rows == _UNDER_CAP_ROWS


@patch("scene_common.glb_top_view.rendering.OffscreenRenderer")
def test_render_top_view_rejects_empty_tensor_mesh_before_renderer(mock_renderer_cls):
  """Empty tensor_mesh fails before OffscreenRenderer (avoids native EGL crash)."""
  with pytest.raises(ValueError, match="tensor_mesh is empty"):
    renderTopView(MagicMock(), [], np.array([1.0, 1.0, 1.0]), 64, 48)
  mock_renderer_cls.assert_not_called()


@pytest.mark.parametrize("columns,rows", [
  (_WIDE_COLUMNS, _WIDE_ROWS),
  (_TALL_COLUMNS, _TALL_ROWS),
])
def test_material_to_material_record_caps_oversized_albedo(columns, rows):
  """Autocalibration path shares the same upload cap and does not mutate source."""
  source = _texture_image(columns, rows)
  mat = SimpleNamespace(
    vector_properties={},
    scalar_properties={},
    texture_maps={"albedo": source},
  )

  with patch("scene_common.glb_top_view.VECTOR_PROPERTIES", []), \
       patch("scene_common.glb_top_view.SCALAR_PROPERTIES", []):
    mat_record = materialToMaterialRecord(mat)

  capped_cols, capped_rows = _legacy_shape(mat_record.albedo_img)
  _assert_capped_aspect(capped_cols, capped_rows, columns, rows)
  assert source.columns == columns
  assert source.rows == rows
