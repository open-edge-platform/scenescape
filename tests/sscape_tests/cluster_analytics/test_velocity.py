#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for analyze_cluster_velocity / classify_movement_pattern
in ClusterAnalyticsContext.
"""

import numpy as np
import pytest


def _obj(x, y, vx, vy, vz=0.0):
  """Build a minimal detection object."""
  return {
    "id": f"obj-{x}-{y}",
    "translation": [x, y, 0.0],
    "velocity": [vx, vy, vz],
  }


class TestAnalyzeClusterVelocity:

  def test_zero_velocity_is_stationary(self, context):
    objects = [_obj(0.0, 0.0, 0.0, 0.0), _obj(1.0, 0.0, 0.0, 0.0),
               _obj(0.0, 1.0, 0.0, 0.0), _obj(1.0, 1.0, 0.0, 0.0)]
    center = np.array([0.5, 0.5])

    result = context.analyze_cluster_velocity(objects, center)

    assert result["movement_type"] == "stationary"

  def test_identical_velocities_are_coordinated_parallel(self, context):
    objects = [_obj(0.0, 0.0, 1.0, 0.0), _obj(1.0, 0.0, 1.0, 0.0),
               _obj(0.0, 1.0, 1.0, 0.0), _obj(1.0, 1.0, 1.0, 0.0)]
    center = np.array([0.5, 0.5])

    result = context.analyze_cluster_velocity(objects, center)

    assert result["movement_type"] == "coordinated_parallel"

  def test_velocities_toward_center_are_converging(self, context):
    # Objects all to the right of origin, velocities obliquely toward center.
    # Asymmetric placement keeps avg_velocity non-zero (> STATIONARY_THRESHOLD)
    # while the y-component spread keeps velocity_coherence low enough to
    # pass the coordinated_parallel check and fall through to convergence scoring.
    objects = [
      _obj(3.0, 0.0, -2.0, 3.0),
      _obj(3.0, 1.0, -2.0, -3.0),
      _obj(4.0, 0.0, -3.0, 2.0),
      _obj(4.0, -1.0, -3.0, -2.0),
    ]
    center = np.array([0.0, 0.0])

    result = context.analyze_cluster_velocity(objects, center)

    assert result["movement_type"] == "converging"

  def test_velocities_away_from_center_are_diverging(self, context):
    # Objects near origin, velocities obliquely away from center.
    # Asymmetric y-components keep coherence low so divergence scoring is reached.
    objects = [
      _obj(1.0, 0.0, 4.0, -6.0),
      _obj(1.0, 0.5, 4.0, 6.0),
      _obj(1.5, 0.0, 6.0, -4.0),
      _obj(1.5, -0.5, 6.0, 4.0),
    ]
    center = np.array([0.0, 0.0])

    result = context.analyze_cluster_velocity(objects, center)

    assert result["movement_type"] == "diverging"

  def test_fewer_than_two_objects_is_insufficient(self, context):
    objects = [_obj(0.0, 0.0, 1.0, 0.0)]
    center = np.array([0.0, 0.0])

    result = context.analyze_cluster_velocity(objects, center)

    assert result["movement_type"] == "insufficient_data"

  def test_result_contains_expected_keys(self, context):
    objects = [_obj(0.0, 0.0, 0.5, 0.5), _obj(1.0, 0.0, 0.5, 0.5)]
    center = np.array([0.5, 0.0])

    result = context.analyze_cluster_velocity(objects, center)

    for key in ("movement_type", "average_velocity", "velocity_magnitude",
                "movement_direction_degrees", "velocity_coherence"):
      assert key in result, f"Missing key: {key}"

  def test_average_velocity_has_three_components(self, context):
    objects = [_obj(0.0, 0.0, 1.0, 2.0, 3.0), _obj(1.0, 0.0, 1.0, 2.0, 3.0)]
    center = np.array([0.5, 0.0])

    result = context.analyze_cluster_velocity(objects, center)

    assert len(result["average_velocity"]) == 3
    assert abs(result["average_velocity"][0] - 1.0) < 1e-6
    assert abs(result["average_velocity"][1] - 2.0) < 1e-6

  def test_object_missing_velocity_is_skipped(self, context):
    objects = [
      {"id": "no-vel", "translation": [0.0, 0.0, 0.0]},
      _obj(1.0, 0.0, 1.0, 0.0),
      _obj(2.0, 0.0, 1.0, 0.0),
    ]
    center = np.array([1.0, 0.0])

    # Should not raise; object without velocity is silently skipped
    result = context.analyze_cluster_velocity(objects, center)
    assert "movement_type" in result
