# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generated meshes are exported y-up, like every uploaded GLB, so a downloaded map can be re-uploaded as is."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import trimesh

from manager.mesh_generator import MeshGenerator
from manager.models import Scene
from scene_common.glb_top_view import getMeshSize
from scene_common.mesh_util import extractMeshFromGLB

FLOOR_EXTENTS = (4.0, 3.0, 1.0)


def _save_generated_box(tmp_path):
  box = trimesh.creation.box(extents=FLOOR_EXTENTS)
  box.apply_translation(box.extents / 2)
  scene = Scene(name="gen")
  # Stale values from an earlier upload must not leak into the generated map
  scene.rotation_z = 15.0
  scene.translation_x = 5.0
  exported = {}
  scene.map = MagicMock()
  scene.map.save.side_effect = lambda name, content, save: exported.update(data=content.read())

  with patch.object(Scene, "save"):
    MeshGenerator()._saveMeshToScene(scene, box)

  glb_path = tmp_path / "generated.glb"
  glb_path.write_bytes(exported["data"])
  return scene, box, glb_path


def test_generated_mesh_is_exported_y_up_and_restored_by_scene_rotation(tmp_path):
  scene, box, glb_path = _save_generated_box(tmp_path)

  raw = trimesh.load(str(glb_path), force="mesh")
  assert raw.extents == pytest.approx((FLOOR_EXTENTS[0], FLOOR_EXTENTS[2], FLOOR_EXTENTS[1]), abs=1e-4)

  assert (scene.rotation_x, scene.rotation_y, scene.rotation_z) == (Scene.DEFAULT_MESH_ROTATION, 0.0, 0.0)
  assert (scene.translation_x, scene.translation_y, scene.translation_z) == (0.0, 0.0, 0.0)

  mesh, _ = extractMeshFromGLB(str(glb_path), rotation=np.array([scene.rotation_x, scene.rotation_y, scene.rotation_z]))
  assert getMeshSize(mesh) == pytest.approx(FLOOR_EXTENTS, abs=1e-4)
  assert mesh.get_axis_aligned_bounding_box().min_bound.numpy() == pytest.approx((0.0, 0.0, 0.0), abs=1e-4)


def test_generated_mesh_export_does_not_mutate_the_input_mesh(tmp_path):
  _, box, _ = _save_generated_box(tmp_path)

  assert box.bounds == pytest.approx(np.array([[0.0, 0.0, 0.0], FLOOR_EXTENTS]), abs=1e-6)
