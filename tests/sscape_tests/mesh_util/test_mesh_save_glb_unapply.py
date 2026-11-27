# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generated mesh save disables every GLB layer before overwriting scene.map."""

from unittest.mock import MagicMock, patch

import pytest
import trimesh

from manager.mesh_generator import MeshGenerator


@pytest.mark.django_db
@pytest.mark.parametrize("use_glb_map", [True, False])
@patch("manager.mesh_generator.glb_state")
def test_save_mesh_disables_glb_layers_before_overwriting_map(mock_glb, use_glb_map):
  order = []
  mock_glb.disable_all_layers.side_effect = lambda _scene: order.append("disable")
  scene = MagicMock(name="scene", use_glb_map=use_glb_map)
  scene.map.save.side_effect = lambda *_args, **_kwargs: order.append("save")

  MeshGenerator()._saveMeshToScene(scene, trimesh.creation.box())

  assert order == ["disable", "save"]
  mock_glb.disable_all_layers.assert_called_once_with(scene)
  mock_glb.lock_scene_row.assert_called_once_with(scene)
  scene.refresh_from_db.assert_called_once()
  scene.save.assert_called_once()
