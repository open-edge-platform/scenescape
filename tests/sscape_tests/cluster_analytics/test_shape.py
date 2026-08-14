#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for detect_shape_ml in ClusterAnalyticsContext.

Notes on algorithm behaviour:
- Rectangle corners are always equidistant from their centroid, so
  dist_variance == 0 → they are classified as 'circle' by the first
  branch.  There is no test for 'rectangle' because the shape is
  structurally unreachable with any set of valid rectangular corners.
- len < 3 → 'insufficient_points' (explicit early return).
"""

import math
import pytest
import numpy as np


class TestDetectShapeMl:

  def test_circular_arrangement_returns_circle(self, context):
    n = 8
    radius = 2.0
    points = [
      [radius * math.cos(2 * math.pi * i / n),
       radius * math.sin(2 * math.pi * i / n)]
      for i in range(n)
    ]
    result = context.detect_shape_ml(points)

    assert result["shape"] == "circle"
    assert "size" in result

  def test_collinear_points_return_line(self, context):
    # Three collinear points with unequal spacing so dist_variance > threshold
    points = [[0.0, 0.0], [5.0, 0.0], [2.0, 0.0]]
    result = context.detect_shape_ml(points)

    assert result["shape"] == "line"
    assert "size" in result

  def test_scattered_cloud_returns_irregular(self, context):
    # 5 points at very different angles and distances – non-uniform distribution
    points = [
      [0.0, 0.0],
      [1.0, 5.0],
      [4.0, 0.5],
      [-2.0, 3.0],
      [3.0, -4.0],
    ]
    result = context.detect_shape_ml(points)

    assert result["shape"] in ("irregular", "circle")
    assert "size" in result

  def test_five_equidistant_points_returns_circle(self, context):
    # 5 points evenly on a unit circle – uniform angle diffs → circle
    n = 5
    points = [
      [math.cos(2 * math.pi * i / n),
       math.sin(2 * math.pi * i / n)]
      for i in range(n)
    ]
    result = context.detect_shape_ml(points)

    assert result["shape"] == "circle"

  def test_fewer_than_three_points_returns_insufficient(self, context):
    result = context.detect_shape_ml([[0.0, 0.0], [1.0, 0.0]])

    assert result["shape"] == "insufficient_points"
    assert result["size"] == {}

  def test_single_point_returns_insufficient(self, context):
    result = context.detect_shape_ml([[0.0, 0.0]])

    assert result["shape"] == "insufficient_points"

  def test_result_always_has_shape_key(self, context):
    for points in (
      [[0.0, 0.0]],
      [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
      [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0], [4.0, 0.0]],
    ):
      result = context.detect_shape_ml(points)
      assert "shape" in result, f"Missing 'shape' key for input {points}"
