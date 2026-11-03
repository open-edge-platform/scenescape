# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GLB auto-alignment places the mesh min corner at the scene origin."""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import open3d as o3d
import pytest

from manager.models import Scene


def _box(size, origin):
  legacy = o3d.geometry.TriangleMesh.create_box(*size)
  legacy.translate(origin)
  return o3d.t.geometry.TriangleMesh.from_legacy(legacy)


def _scene_stub(path="scene.glb"):
  return SimpleNamespace(
    map=SimpleNamespace(path=path),
    _from_generate_mesh=False,
    rotation_x=0.0,
    rotation_y=0.0,
    rotation_z=0.0,
    translation_x=0.0,
    translation_y=0.0,
    translation_z=0.0,
  )


def _translation(scene):
  return (scene.translation_x, scene.translation_y, scene.translation_z)


class TestAutoAlignSceneMapTranslation:

  @pytest.mark.parametrize("origin", [
    [0.0, 0.0, 0.0],
    [5.0, -3.0, 2.0],
  ])
  @patch("manager.models.extractMeshFromGLB")
  def test_translation_is_negative_min_corner(self, mock_extract, origin):
    mock_extract.return_value = (_box((10.0, 4.0, 1.0), origin), [])
    scene = _scene_stub()

    width, height, depth = Scene.autoAlignSceneMap(scene)

    assert (width, height, depth) == pytest.approx((10.0, 4.0, 1.0))
    assert _translation(scene) == pytest.approx(tuple(-np.array(origin)))

  @patch("manager.models.extractMeshFromGLB")
  def test_centred_mesh_keeps_half_extent_translation(self, mock_extract):
    mock_extract.return_value = (_box((10.0, 4.0, 1.0), [-5.0, -2.0, -0.5]), [])
    scene = _scene_stub()

    Scene.autoAlignSceneMap(scene)

    assert _translation(scene) == pytest.approx((5.0, 2.0, 0.5))

  @patch("manager.models.extractMeshFromGLB")
  def test_non_glb_map_is_left_alone(self, mock_extract):
    scene = _scene_stub(path="scene.obj")
    scene.translation_x = 7.0

    assert Scene.autoAlignSceneMap(scene) is None

    mock_extract.assert_not_called()
    assert scene.translation_x == 7.0

  @patch("manager.models.extractMeshFromGLB")
  def test_generated_mesh_is_not_realigned(self, mock_extract):
    scene = _scene_stub()
    scene._from_generate_mesh = True
    scene.translation_x = 7.0

    assert Scene.autoAlignSceneMap(scene) is None

    mock_extract.assert_not_called()
    assert scene.translation_x == 7.0
