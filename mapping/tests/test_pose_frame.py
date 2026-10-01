# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pose priors handed to MapAnything must be expressed in the model's world frame.
The service rotates output poses and geometry by 180° about X; input priors
must receive the same rotation or the conditioned views land mirrored.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from mapanything_model import MapAnythingModel
from model_interface import ReconstructionModel


def _pose(t, rot=None):
  P = np.eye(4)
  if rot is not None:
    P[:3, :3] = rot
  P[:3, 3] = t
  return P


def test_scene_to_model_world_is_x_180_and_self_inverse():
  R = MapAnythingModel.SCENE_TO_MODEL_WORLD
  assert np.allclose(R @ R, np.eye(4))
  # +Y and +Z flip, X unchanged
  assert np.allclose(R @ np.array([1, 2, 3, 1]), [1, -2, -3, 1])


def test_input_prior_round_trips_through_output_convention():
  """prior (scene) -> model world -> output rotation == prior (scene)."""
  Rx = MapAnythingModel.SCENE_TO_MODEL_WORLD
  rng = np.random.default_rng(3)
  for _ in range(5):
    q = rng.normal(size=4); q /= np.linalg.norm(q)
    x, y, z, w = q
    rot = ReconstructionModel.pose_from_location(
      None, {"translation": [0, 0, 0], "rotation": [x, y, z, w]})[:3, :3]
    scene_pose = _pose(rng.normal(size=3), rot)
    model_pose = Rx @ scene_pose          # what _preprocess_images now sends in
    back_out = Rx @ model_pose            # what _process_outputs applies on the way out
    assert np.allclose(back_out, scene_pose)


def test_preprocess_rotates_priors_but_not_images(monkeypatch):
  """_preprocess_images applies SCENE_TO_MODEL_WORLD to every non-None pose."""
  import types
  import mapanything_model as mm

  captured = {}

  class _Tensor:
    def __init__(self, a): self.a = a
    def __getitem__(self, k): return self
  # Stub torch and MapAnything helpers so no model/GPU is needed.
  fake_torch = types.SimpleNamespace(from_numpy=lambda a: _Tensor(a))
  monkeypatch.setattr(mm, "torch", fake_torch, raising=False)
  monkeypatch.setattr(mm, "crop_resize_if_necessary",
                      lambda img, resolution: [img], raising=False)
  monkeypatch.setattr(mm, "find_closest_aspect_ratio",
                      lambda ar, s: (518, 392), raising=False)
  monkeypatch.setattr(mm, "IMAGE_NORMALIZATION_DICT",
                      {"dinov2": types.SimpleNamespace(mean=0, std=1)}, raising=False)
  monkeypatch.setattr(mm, "tvf", types.SimpleNamespace(
    Compose=lambda fns: (lambda im: _Tensor(im)), ToTensor=lambda: None,
    Normalize=lambda mean, std: None), raising=False)

  model = MapAnythingModel.__new__(MapAnythingModel)
  from PIL import Image
  imgs = [Image.new("RGB", (640, 480)) for _ in range(2)]
  scene_poses = [_pose([1, 2, 3]), None]
  views = model._preprocess_images(imgs, None, scene_poses)

  sent = views[0]["camera_poses"].a
  assert np.allclose(sent, MapAnythingModel.SCENE_TO_MODEL_WORLD @ scene_poses[0])
  assert np.allclose(sent[:3, 3], [1, -2, -3])
  assert "camera_poses" not in views[1]
