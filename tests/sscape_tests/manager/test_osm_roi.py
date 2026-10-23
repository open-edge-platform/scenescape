# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pure-function unit tests for OSM ROI bounds filtering and width/geometry
derivation (no DB needed)."""

import numpy as np
import pytest

from manager import osm_roi
from scene_common.earth_lla import convertLLAToECEF

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


@pytest.mark.parametrize(
  ("tags", "way_type", "expected"),
  [
    ({"width": "0"}, "secondary", 8.0),    # zero width falls back to type default
    ({"width": "-5"}, "secondary", 8.0),   # negative width falls back to type default
    ({"width": "nan"}, "secondary", 8.0),  # non-finite width falls back to type default
    ({"width": "inf"}, "secondary", 8.0),  # non-finite width falls back to type default
    ({"lanes": "0"}, "secondary", 8.0),    # zero lanes falls back to type default
    ({"lanes": "-2"}, "secondary", 8.0),   # negative lanes falls back to type default
    ({"lanes": "1" * 400}, "secondary", 8.0),   # lanes * lane width overflows float; falls back
    ({"lanes": "1" * 5000}, "secondary", 8.0),  # beyond int parsing limit; falls back
    ({"width": "7.5"}, "secondary", 7.5),  # positive explicit width is honored
    ({"lanes": "2"}, "secondary", 7.0),    # positive lane count is honored (2 * 3.5)
    ({"lanes": "0"}, "footway", 3.0),      # lanes ignored for non-lane-based types
  ],
)
def test_get_width_m_rejects_nonpositive_or_nonfinite_widths(tags, way_type, expected):
  assert osm_roi.get_width_m(tags, way_type) == expected


def test_line_to_polygons_skips_degenerate_zero_width_buffer():
  # A zero-width buffer produces an empty polygon; it must be dropped instead
  # of appended as a preview with points == [] (which would later blow up
  # roi_overlaps_bounds's Polygon(points) construction).
  polygons = osm_roi.line_to_polygons([(0, 0), (10, 0)], width_m=0)

  assert polygons == []


def test_line_to_polygons_then_roi_overlaps_bounds_does_not_raise():
  # End-to-end regression for the "lanes=0 / width=0" crash: previews built
  # from a zero width must never reach roi_overlaps_bounds with degenerate
  # points, since filter_by_bounds is run on whatever line_to_polygons yields.
  width_m = osm_roi.get_width_m({"lanes": "0"}, "secondary")
  polygons = osm_roi.line_to_polygons([(0, 0), (10, 0)], width_m)

  assert all(len(points) >= 3 for points in polygons)
  for points in polygons:
    osm_roi.roi_overlaps_bounds(points, BOUNDS)


def test_bbox_from_map_corners_rejects_antimeridian_crossing():
  corners = [[10.0, 179.9999, 0], [10.001, 179.9999, 0], [10.001, -179.9999, 0], [10.0, -179.9999, 0]]

  with pytest.raises(osm_roi.OsmRoiError, match="antimeridian"):
    osm_roi.bbox_from_map_corners(corners)


def test_bbox_from_map_corners_regular_scene():
  corners = [[10.0, 20.0, 0], [10.001, 20.0, 0], [10.001, 20.001, 0], [10.0, 20.001, 0]]

  assert osm_roi.bbox_from_map_corners(corners) == (10.0, 20.0, 10.001, 20.001)


def test_lla_to_local_xy_inverts_trs_matrix():
  trs = np.eye(4)
  trs[:3, 3] = convertLLAToECEF([10.0, 20.0, 0.0])
  expected = convertLLAToECEF([10.0001, 20.0001, 0.0]) - trs[:3, 3]

  x, y = osm_roi.lla_to_local_xy(trs.tolist(), 10.0001, 20.0001)

  assert (x, y) == pytest.approx((expected[0], expected[1]))


def test_lla_to_local_xy_requires_trs_matrix():
  with pytest.raises(osm_roi.OsmRoiError):
    osm_roi.lla_to_local_xy(None, 10.0, 20.0)
