# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""bake_layers: several placed GLB layers become one textured GLB with the same footprint."""

import io

import numpy as np
import pytest
import trimesh
from PIL import Image

from manager.glb_bake import bake_layers
from scene_common.mesh_util import extractMeshFromGLB, getPosedMeshFootprint

LAYER_A = ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
LAYER_B = ([0.0, 0.0, 90.0], [6.0, -3.0, 0.5])


def _textured_glb(path, size, color):
  mesh = trimesh.creation.box(extents=(size, size, size))
  uv = np.zeros((len(mesh.vertices), 2))
  material = trimesh.visual.material.PBRMaterial(baseColorTexture=Image.new('RGB', (4, 4), color))
  mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
  path.write_bytes(mesh.export(file_type='glb'))
  return str(path)


@pytest.fixture
def layer_files(tmp_path):
  return (
    _textured_glb(tmp_path / 'a.glb', 2.0, (255, 0, 0)),
    _textured_glb(tmp_path / 'b.glb', 4.0, (0, 0, 255)),
  )


def _footprint(glb_path, rotation, translation):
  mesh, _ = extractMeshFromGLB(glb_path, rotation=None)
  return getPosedMeshFootprint(mesh, rotation, translation)


def _loaded_geometries(baked):
  scene = trimesh.load(io.BytesIO(baked), file_type='glb')
  return list(scene.geometry.values())


def test_bake_keeps_textures(layer_files):
  (path_a, path_b) = layer_files
  baked = bake_layers([(path_a, *LAYER_A), (path_b, *LAYER_B)])

  geometries = _loaded_geometries(baked)
  assert geometries
  assert all(geometry.visual.kind == 'texture' for geometry in geometries)


def test_bake_footprint_is_union_of_posed_layers(layer_files, tmp_path):
  (path_a, path_b) = layer_files
  baked = bake_layers([(path_a, *LAYER_A), (path_b, *LAYER_B)])
  baked_path = str(tmp_path / 'baked.glb')
  with open(baked_path, 'wb') as f:
    f.write(baked)

  expected = np.vstack([_footprint(path_a, *LAYER_A), _footprint(path_b, *LAYER_B)])
  expected_min = expected[:, :2].min(axis=0)
  expected_max = expected[:, :2].max(axis=0)

  baked_footprint = _footprint(baked_path, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
  assert np.allclose(baked_footprint[:, :2].min(axis=0), expected_min, atol=1e-3)
  assert np.allclose(baked_footprint[:, :2].max(axis=0), expected_max, atol=1e-3)
