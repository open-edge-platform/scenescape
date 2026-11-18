# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit coverage for Observation Processor numerical and cache helpers."""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from observation_processor.conditioning import (
  UNOBSERVABLE_SIGMA, condition_depths, measurement_covariance,
)
from observation_processor.scene_provider import SceneProvider


def test_condition_depths_validates_only_observable_values():
  observations = {
    "depth_est": np.array([3.0, -1.0]),
    "depth_sigma": np.array([2.0, UNOBSERVABLE_SIGMA]),
  }
  depth, variance, observable = condition_depths(observations, None, full=False)
  np.testing.assert_array_equal(observable, [True, False])
  np.testing.assert_array_equal(depth, [3.0, -1.0])
  np.testing.assert_array_equal(variance, [4.0, 0.0])

  observations["depth_est"][0] = -1.0
  with pytest.raises(ValueError, match="measurable depth"):
    condition_depths(observations, None, full=False)


def test_snapshot_keeps_frame_consistent_across_refresh():
  scene = {"uid": "scene", "map": "/media/floor.png"}
  rest = Mock()
  for method, records in (("getScenes", [scene]), ("getCameras", []), ("getAssets", [])):
    result = getattr(rest, method).return_value
    result.statusCode = 200
    result.get.return_value = records

  with patch("observation_processor.scene_provider.RESTClient", return_value=rest):
    provider = SceneProvider()
    provider.warm()
    snapshot = provider.snapshot()
    original = snapshot.get_scene("scene")
    scene["map"] = "/media/changed.png"
    provider.invalidate()
    provider.warm()

  assert snapshot.get_scene("scene") == original
  assert snapshot.get_scene("scene")["map"] == "/media/floor.png"
  assert provider.get_scene("scene")["map"] == "/media/changed.png"


def test_covariance_replacement_preserves_lateral_noise():
  ray = np.array([1.0, 2.0, 3.0])
  ray /= np.linalg.norm(ray)
  covariance = 0.3 * np.eye(3) + 10 * np.outer(ray, ray)
  output = measurement_covariance(covariance, ray, 0)
  expected = 0.3 * (np.eye(3) - np.outer(ray, ray)) \
      + 1e-4 * np.outer(ray, ray)
  np.testing.assert_allclose(output[:3, :3], expected)
  assert np.linalg.eigvalsh(output).min() > 0
