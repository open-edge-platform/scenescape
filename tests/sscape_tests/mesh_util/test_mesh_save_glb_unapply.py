# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generated mesh save restores an applied GLB map before overwriting scene.map."""

from unittest.mock import MagicMock, patch

import pytest
import trimesh

from manager.mesh_generator import MeshGenerator


@pytest.mark.parametrize("use_glb_map", [True, False])
@patch("manager.mesh_generator.glb_alignment")
def test_save_mesh_unapplies_glb_only_before_overwriting_map(mock_glb, use_glb_map):
  order = []
  mock_glb.unapply_glb_map.side_effect = lambda _scene: order.append("unapply")
  scene = MagicMock(name="scene", use_glb_map=use_glb_map)
  scene.map.save.side_effect = lambda *_args, **_kwargs: order.append("save")

  MeshGenerator()._saveMeshToScene(scene, trimesh.creation.box())

  expected = ["unapply", "save"] if use_glb_map else ["save"]
  assert order == expected
  if use_glb_map:
    mock_glb.unapply_glb_map.assert_called_once_with(scene)
