#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Re-uploading a generated map through the REST API keeps the scene horizontal.

A full mesh generation through the mapping service is not available in this
profile, so the generated-map GLB is built on the host with the same y-up export
transform that MeshGenerator._saveMeshToScene applies.
"""

import io
from http import HTTPStatus
from urllib.parse import urlparse

import numpy as np
import pytest
import trimesh

from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

FLOOR_EXTENTS = (4.0, 3.0, 1.0)
GENERATED_MESH_ROTATION = [90, 0, 0]


def _generated_map_glb():
  floor = trimesh.creation.box(extents=FLOOR_EXTENTS)
  floor.apply_translation(floor.extents / 2)
  floor.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
  return floor.export(file_type="glb")


# TODO: replace the placeholder with a real Zephyr ID; make check-zephyr-ids fails until then.
@pytest.mark.test_name("NEX-T31544")
def test_generated_map_reupload_keeps_scene_horizontal(rest, params, scene_factory, result_recorder):
  scene = scene_factory("GeneratedMapReupload")

  res = rest.updateScene(scene["uid"], {
    "name": "GeneratedMapReupload",
    "map": ("generated_mesh.glb", _generated_map_glb()),
  })
  assert res.statusCode == HTTPStatus.OK, f"Map upload failed: {res.errors}"

  stored = rest.getScene(scene["uid"])
  assert stored.statusCode == HTTPStatus.OK, f"Failed to read scene: {stored.errors}"
  assert stored["mesh_rotation"] == GENERATED_MESH_ROTATION
  assert stored["mesh_translation"] == pytest.approx([0, 0, 0], abs=1e-4)

  map_url = f"{params['weburl']}{urlparse(stored['map']).path}"
  reply = rest.session.get(map_url, headers={"Authorization": f"Token {rest.token}"},
                           verify=rest.verify_ssl, timeout=rest.timeout)
  assert reply.status_code == HTTPStatus.OK, f"Map download failed: {reply.status_code}"

  mesh = trimesh.load(io.BytesIO(reply.content), file_type="glb", force="mesh")
  mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(stored["mesh_rotation"][0]), [1, 0, 0]))
  mesh.apply_translation(stored["mesh_translation"])
  assert mesh.extents == pytest.approx(FLOOR_EXTENTS, abs=1e-4)
  assert mesh.bounds[0] == pytest.approx([0, 0, 0], abs=1e-4)

  result_recorder.success()
