# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for SceneModel.reloadMapIfChanged."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scene_common.scene_model import SceneModel

TEST_GLB_FILE = Path(__file__).resolve().parents[1] / "mesh_util" / "test_data" / "scene.glb"


def _write_png(path):
  Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(path)


def _write_glb(path):
  shutil.copy(TEST_GLB_FILE, path)


def _x_extent(mesh):
  return float(np.ptp(mesh.vertex.positions.numpy()[:, 0]))


class TestReloadMapIfChanged:

  def test_unchanged_map_and_scale_keeps_loaded_map(self, tmp_path):
    png = str(tmp_path / 'map.png')
    _write_png(png)
    scene = SceneModel('policy', png, 10.0)
    mesh = scene.map_triangle_mesh
    background = scene.background
    assert mesh is not None
    assert background is not None

    assert scene.reloadMapIfChanged(png, 10.0) is False

    assert scene.map_triangle_mesh is mesh
    assert scene.background is background

  def test_map_changed_from_png_to_glb_replaces_background_and_mesh(self, tmp_path):
    png = str(tmp_path / 'map.png')
    glb = str(tmp_path / 'map.glb')
    _write_png(png)
    _write_glb(glb)
    scene = SceneModel('policy', png, 10.0)
    png_mesh = scene.map_triangle_mesh

    assert scene.reloadMapIfChanged(glb, 10.0) is True

    assert scene.map_file == glb
    assert scene.background is None
    assert scene.map_triangle_mesh is not None
    assert scene.map_triangle_mesh is not png_mesh
    assert _x_extent(scene.map_triangle_mesh) != pytest.approx(_x_extent(png_mesh))

  def test_map_changed_from_glb_to_png_replaces_background_and_mesh(self, tmp_path):
    png = str(tmp_path / 'map.png')
    glb = str(tmp_path / 'map.glb')
    _write_png(png)
    _write_glb(glb)
    scene = SceneModel('policy', glb, None)
    glb_mesh = scene.map_triangle_mesh
    assert scene.background is None

    assert scene.reloadMapIfChanged(png, 10.0) is True

    assert scene.map_file == png
    assert scene.background is not None
    assert scene.map_triangle_mesh is not glb_mesh
    assert _x_extent(scene.map_triangle_mesh) == pytest.approx(8 / 10.0)

  def test_scale_only_change_reloads_mesh(self, tmp_path):
    png = str(tmp_path / 'map.png')
    _write_png(png)
    scene = SceneModel('policy', png, 10.0)
    old_mesh = scene.map_triangle_mesh
    old_extent = _x_extent(old_mesh)

    assert scene.reloadMapIfChanged(png, 20.0) is True

    assert scene.background is not None
    assert scene.map_triangle_mesh is not old_mesh
    assert _x_extent(scene.map_triangle_mesh) == pytest.approx(old_extent / 2)
