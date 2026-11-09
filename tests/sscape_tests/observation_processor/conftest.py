# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Import paths for Observation Processor unit tests."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import open3d as o3d
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
for source in (
  REPO_ROOT / "observation_processor" / "src",
  REPO_ROOT / "spatial_performance_primitives",
  REPO_ROOT / "spatial_performance_primitives" / "frustum_gaussian" / "python",
):
  if str(source) not in sys.path:
    sys.path.insert(0, str(source))

from observation_processor.conditioning import process_detections
from observation_processor.grpc_api import observation_processor_pb2 as pb
from observation_processor.scene_provider import SceneProvider


def _fake_frustum_observations(boxes):
  count = len(boxes)
  return {
    "mu": np.zeros((count, 3)),
    "Sigma": np.tile(np.eye(3), (count, 1, 1)),
    "ray": np.tile([0.0, 0.0, -1.0], (count, 1)),
    "depth_est": np.full(count, 2.0),
    "depth_sigma": np.full(count, 0.1),
    "depth_lo": np.zeros(count),
    "depth_hi": np.full(count, 10.0),
    "score": np.full(count, 0.8),
    "edge_valid": np.full(count, 15, dtype=np.uint8),
  }


class APIResult(dict):
  """Small RESTResult equivalent for isolated REST fixtures."""

  def __init__(self, value=None, status=200):
    super().__init__(value or {})
    self.statusCode = status


@pytest.fixture
def projection_configuration():
  """Warm a real reasoner with a floor mesh, without connecting to a database."""
  scene = {"uid": "scene", "map": "/media/floor.glb"}
  camera = {
    "uid": "camera", "intrinsics": {"fx": 100, "fy": 100, "cx": 64, "cy": 48},
    "translation": [0, 0, 3], "rotation": [180, 0, 0], "resolution": [128, 96],
  }
  assets = [
    {"name": "person", "x_size": 0.6, "y_size": 0.5, "z_size": 1.8},
    {"name": "car", "x_size": 2.0, "y_size": 4.5, "z_size": 1.5,
     "axis_aware_sizing": False, "project_to_map": True},
  ]
  rest = Mock()
  rest.getScenes.side_effect = lambda *args: APIResult({"results": [scene]})
  rest.getScene.side_effect = lambda uid: APIResult(scene) if uid == "scene" \
      else APIResult(status=404)
  rest.getCameras.side_effect = lambda *args: APIResult({"results": [camera]})
  rest.getAssets.side_effect = lambda *args: APIResult({"results": assets})
  mesh = o3d.geometry.TriangleMesh.create_box(width=20, height=20, depth=0.1)
  mesh.translate([-10, -10, -0.1])
  tensor_mesh = o3d.t.geometry.TriangleMesh.from_legacy(mesh)
  projector = Mock(side_effect=lambda *args, **kwargs:
                   _fake_frustum_observations(kwargs["boxes"]))
  transformer = Mock(side_effect=lambda observations, pose: observations)
  with patch("observation_processor.scene_provider.RESTClient", return_value=rest), \
       patch.object(SceneProvider, "_mesh_bytes", return_value=b"floor mesh"), \
       patch.object(SceneProvider, "_load_world_mesh", return_value=tensor_mesh) as load, \
       patch("observation_processor.conditioning.fg.project_frustum_batch", projector), \
       patch("observation_processor.conditioning.fg.transform_to_world_batch", transformer):
    provider = SceneProvider()
    provider.warm()
    yield SimpleNamespace(provider=provider, rest=rest, scene=scene, camera=camera,
                assets=assets, mesh=tensor_mesh, load=load,
                projector=projector, transformer=transformer)


@pytest.fixture
def frame():
  """A valid mixed-category-capable input frame."""
  request = pb.ProcessDetectionsRequest(
    scene_id="scene", camera_id="camera", mode=pb.CONDITIONING_MODE_FRUSTUM_ONLY,
    include_diagnostics=True)
  request.timestamp.seconds = 1234567890
  request.timestamp.nanos = 123456789
  request.detections.add(
    detection_id="detection", category="person",
    bounding_box_px=pb.BoundingBoxPx(x=54, y=25, width=20, height=46))
  return request


@pytest.fixture
def process_frame(projection_configuration):
  """Run the projection pipeline in-process without starting a gRPC server."""
  return lambda request: process_detections(request, projection_configuration.provider)
