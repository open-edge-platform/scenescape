# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pure-function unit tests for OSM ROI bounds filtering (no DB needed)."""

import pytest

from manager import osm_roi

BOUNDS = {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10}


@pytest.mark.parametrize(
  ("points", "expected"),
  [
    ([(1, 1), (2, 1), (2, 2)], True),        # fully inside
    ([(-5, -5), (5, 5), (5, -5)], True),     # straddles a corner
    ([(20, 20), (21, 20), (21, 21)], False), # fully outside, no overlap
    ([(10, 10), (11, 10), (11, 11)], True),  # touches the boundary exactly
  ],
)
def test_roi_overlaps_bounds(points, expected):
  assert osm_roi.roi_overlaps_bounds(points, BOUNDS) is expected


def test_filter_by_bounds_keeps_full_unclipped_points():
  previews = [
    {"name": "inside", "points": [(1, 1), (2, 1), (2, 2)]},
    {"name": "straddling", "points": [(-5, -5), (5, 5), (5, -5)]},
    {"name": "outside", "points": [(20, 20), (21, 20), (21, 21)]},
  ]

  result = osm_roi.filter_by_bounds(previews, BOUNDS)

  assert [p["name"] for p in result] == ["inside", "straddling"]
  # Points must be returned unmodified - no clipping to the box.
  straddling = next(p for p in result if p["name"] == "straddling")
  assert straddling["points"] == [(-5, -5), (5, 5), (5, -5)]
