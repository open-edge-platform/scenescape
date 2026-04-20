# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math

import pytest

from scene_common.geometry import getRegionEvents, Region, Point

UUID = "39bd9698-8603-43fb-9cb9-06d9a14e6a24"

def _regular_polygon(n, cx=10, cy=10, r=10):
  """! Generate vertices for a regular n-gon centered at (cx, cy) with radius r. """
  return [
    [cx + r * math.cos(2 * math.pi * i / n),
     cy + r * math.sin(2 * math.pi * i / n)]
    for i in range(n)
  ]

# --- Positive tests: object inside various region types ---

@pytest.mark.parametrize("n_vertices", [3, 4, 5, 10],
                         ids=["triangle", "quad", "pentagon", "decagon"])
def test_object_inside_polygon(n_vertices):
  """! Verify object at polygon center is detected inside for varying vertex counts. """
  pts = _regular_polygon(n_vertices)
  region = Region(UUID, "poly", {"points": pts})
  result = getRegionEvents({"r": region}, [Point(10, 10)])
  assert result["r"] == [0]

def test_object_inside_circle():
  """! Verify object at circle center is detected inside. """
  region = Region(UUID, "circle", {"area": "circle", "center": [5, 5], "radius": 3})
  result = getRegionEvents({"r": region}, [Point(5, 5)])
  assert result["r"] == [0]

def test_object_inside_scene():
  """! Verify any object is inside a scene-wide region. """
  region = Region(UUID, "scene", {"area": "scene"})
  result = getRegionEvents({"r": region}, [Point(100, 200)])
  assert result["r"] == [0]

# --- No-match tests: object outside all regions ---

def test_no_match_outside_polygon():
  """! Verify object outside polygon is not detected. """
  region = Region(UUID, "poly", {"points": [[0, 0], [10, 0], [10, 10], [0, 10]]})
  result = getRegionEvents({"r": region}, [Point(50, 50)])
  assert result["r"] == []

def test_no_match_outside_circle():
  """! Verify object outside circle is not detected. """
  region = Region(UUID, "circle", {"area": "circle", "center": [5, 5], "radius": 3})
  result = getRegionEvents({"r": region}, [Point(50, 50)])
  assert result["r"] == []

# --- Length variations ---

def test_single_region_single_object():
  """! Verify single region with one matching object. """
  region = Region(UUID, "poly", {"points": [[0, 0], [10, 0], [10, 10], [0, 10]]})
  result = getRegionEvents({"r": region}, [Point(5, 5)])
  assert result["r"] == [0]

def test_multiple_regions_multiple_objects():
  """! Verify correct mapping with overlapping regions and multiple objects. """
  region_a = Region(UUID, "a", {"points": [[0, 0], [10, 0], [10, 10], [0, 10]]})
  region_b = Region(UUID, "b", {"points": [[5, 5], [15, 5], [15, 15], [5, 15]]})
  region_c = Region(UUID, "c", {"area": "circle", "center": [20, 20], "radius": 2})
  regions = {"a": region_a, "b": region_b, "c": region_c}
  objects = [Point(7, 7), Point(2, 2), Point(20, 20), Point(50, 50)]
  result = getRegionEvents(regions, objects)
  assert sorted(result["a"]) == [0, 1]
  assert result["b"] == [0]
  assert result["c"] == [2]

# --- Empty inputs ---

def test_empty_object_list():
  """! Verify regions with no objects returns empty lists per key. """
  region = Region(UUID, "poly", {"points": [[0, 0], [10, 0], [10, 10], [0, 10]]})
  result = getRegionEvents({"r": region}, [])
  assert result["r"] == []

def test_empty_region_dict():
  """! Verify empty region dict returns empty result. """
  result = getRegionEvents({}, [Point(5, 5)])
  assert result == {}
