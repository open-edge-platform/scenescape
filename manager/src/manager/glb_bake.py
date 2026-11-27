# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bake several placed GLB layers into one GLB, so the scene map keeps a single identity-posed mesh."""

import trimesh

from scene_common.mesh_util import mergeMesh
from scene_common.transform import CameraPose


def bake_layers(layers):
  """Concatenate GLB layers, each moved by its own pose, into one GLB.

  @param  layers  list of (glb_path, rotation, translation) in draw order; rotation is the
                  Euler XYZ degrees and translation the metres from compute_glb_pose_and_corners
  @return  the baked GLB as bytes; textures are kept
  """
  parts = []
  for glb_path, rotation, translation in layers:
    mesh = mergeMesh(trimesh.load(glb_path)).copy()
    mesh.apply_transform(CameraPose._poseToPoseMat(translation, rotation, [1.0, 1.0, 1.0]))
    parts.append(mesh)
  baked = trimesh.util.concatenate(parts)
  if any(part.visual.kind == 'texture' for part in parts) and baked.visual.kind != 'texture':
    raise ValueError('Baking lost materials or textures during visual concatenation.')
  return baked.export(file_type='glb')
