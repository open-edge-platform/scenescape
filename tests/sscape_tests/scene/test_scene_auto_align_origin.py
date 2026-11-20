# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GLB auto-alignment puts the mesh min corner at the scene origin, centred file or not."""

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


def _scene_stub():
  return SimpleNamespace(
    map=SimpleNamespace(path="scene.glb"),
    _from_generate_mesh=False,
    DEFAULT_MESH_ROTATION=Scene.DEFAULT_MESH_ROTATION,
    rotation_x=0.0, rotation_y=0.0, rotation_z=0.0,
    translation_x=0.0, translation_y=0.0, translation_z=0.0,
  )


@pytest.mark.parametrize("origin", [
  [-5.0, -2.0, -0.5],  # centred on its own origin, like a Polycam scan
  [0.0, 0.0, 0.0],  # min corner at the origin, like an exported generated map
  [5.0, -3.0, 2.0],
])
@patch("manager.models.extractMeshFromGLB")
def test_translation_puts_min_corner_at_origin(mock_extract, origin):
  mock_extract.return_value = (_box((10.0, 4.0, 1.0), origin), [])
  scene = _scene_stub()

  Scene.autoAlignSceneMap(scene)

  assert (scene.translation_x, scene.translation_y, scene.translation_z) == pytest.approx(tuple(-np.array(origin)))
