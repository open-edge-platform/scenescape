# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for validate_map_corners_lla: zero-area rejection and longitude bounds."""

import pytest
from django.core.exceptions import ValidationError

from manager.validators import validate_map_corners_lla


RECTANGLE = [[37.0, -122.0, 0.0], [37.1, -122.0, 0.0], [37.1, -121.9, 0.0], [37.0, -121.9, 0.0]]


@pytest.mark.parametrize("corners", [
  # All four corners identical
  [[37.0, -122.0, 0.0]] * 4,
  # Collinear points on a diagonal line (zero area)
  [[37.0, -122.0, 0.0], [37.1, -121.9, 0.0], [37.2, -121.8, 0.0], [37.3, -121.7, 0.0]],
  # Two coincident pairs (the polygon collapses onto a segment)
  [[37.0, -122.0, 0.0], [37.0, -122.0, 0.0], [37.1, -121.9, 0.0], [37.1, -121.9, 0.0]],
], ids=["identical", "collinear", "coincident_pairs"])
def test_zero_area_corners_rejected(corners):
  """Negative: corners that enclose no area are rejected."""
  with pytest.raises(ValidationError):
    validate_map_corners_lla(corners)


def test_near_degenerate_corners_accepted():
  """Boundary: a very small but non-zero square (about 0.1 m side) is accepted."""
  corners = [
    [37.0, -122.0, 0.0], [37.000001, -122.0, 0.0],
    [37.000001, -121.999999, 0.0], [37.0, -121.999999, 0.0],
  ]
  assert validate_map_corners_lla(corners) == corners


def test_thin_sliver_corners_accepted():
  """Boundary: a thin rectangle with non-zero area is accepted."""
  corners = [
    [37.0, -122.0, 0.0], [37.0 + 1e-9, -122.0, 0.0],
    [37.0 + 1e-9, -121.999, 0.0], [37.0, -121.999, 0.0],
  ]
  assert validate_map_corners_lla(corners) == corners


@pytest.mark.parametrize("corners", [
  # Corner at the western antimeridian bound
  [[10.0, -180.0, 0.0], [11.0, -180.0, 0.0], [11.0, -179.0, 0.0], [10.0, -179.0, 0.0]],
  # Corner at the eastern antimeridian bound
  [[10.0, 179.0, 0.0], [11.0, 179.0, 0.0], [11.0, 180.0, 0.0], [10.0, 180.0, 0.0]],
], ids=["lng_minus_180", "lng_plus_180"])
def test_longitude_bounds_inclusive_accepted(corners):
  """Boundary: longitude of exactly -180 and 180 is accepted."""
  assert validate_map_corners_lla(corners) == corners


def test_longitude_past_antimeridian_rejected():
  """Negative: longitude just beyond 180 is rejected."""
  corners = [[10.0, 179.0, 0.0], [11.0, 179.0, 0.0], [11.0, 180.5, 0.0], [10.0, 180.5, 0.0]]
  with pytest.raises(ValidationError):
    validate_map_corners_lla(corners)


def test_regular_rectangle_accepted():
  """Positive: an ordinary rectangle still validates."""
  assert validate_map_corners_lla(RECTANGLE) == RECTANGLE
