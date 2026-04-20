# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from scene_common.geometry import getTripwireEvents, Tripwire, Point

UUID = "39bd9698-8603-43fb-9cb9-06d9a14e6a24"

# --- Positive tests: crossing in both directions for four orientations ---

@pytest.mark.parametrize(
  "tripwire_pts, current, previous, expected_dir",
  [
    # Horizontal tripwire [(0,0) -> (10,0)]
    ([[0, 0], [10, 0]], Point(5, 1), Point(5, -1), -1),
    ([[0, 0], [10, 0]], Point(5, -1), Point(5, 1), 1),
    # Vertical tripwire [(5,0) -> (5,10)]
    ([[5, 0], [5, 10]], Point(6, 5), Point(4, 5), 1),
    ([[5, 0], [5, 10]], Point(4, 5), Point(6, 5), -1),
    # Acute angle (~45 deg) tripwire [(0,0) -> (10,10)]
    ([[0, 0], [10, 10]], Point(10, 0), Point(0, 10), 1),
    ([[0, 0], [10, 10]], Point(0, 10), Point(10, 0), -1),
    # Obtuse angle (~135 deg) tripwire [(10,0) -> (0,10)]
    ([[10, 0], [0, 10]], Point(0, 0), Point(10, 10), -1),
    ([[10, 0], [0, 10]], Point(10, 10), Point(0, 0), 1),
  ],
  ids=[
    "horizontal-south-to-north",
    "horizontal-north-to-south",
    "vertical-left-to-right",
    "vertical-right-to-left",
    "acute-cross-a",
    "acute-cross-b",
    "obtuse-cross-a",
    "obtuse-cross-b",
  ])
def test_tripwire_crossing(tripwire_pts, current, previous, expected_dir):
  """! Verify tripwire crossing detection for various orientations and directions. """
  tripwire = Tripwire(UUID, "tw", {"points": tripwire_pts})
  result = getTripwireEvents({"tw": tripwire}, [(current, previous)])
  assert len(result["tw"]) == 1
  assert result["tw"][0] == (0, expected_dir)

# --- No-match tests ---

def test_no_crossing_parallel_offset():
  """! Verify no crossing when movement is parallel to tripwire but offset. """
  tripwire = Tripwire(UUID, "tw", {"points": [[0, 0], [10, 0]]})
  result = getTripwireEvents({"tw": tripwire}, [(Point(15, 2), Point(5, 2))])
  assert result["tw"] == []

def test_no_crossing_collinear():
  """! Verify no crossing when movement is along the tripwire (collinear). """
  tripwire = Tripwire(UUID, "tw", {"points": [[0, 0], [10, 0]]})
  result = getTripwireEvents({"tw": tripwire}, [(Point(8, 0), Point(2, 0))])
  assert result["tw"] == []

# --- Positive tests: endpoint on tripwire ---

def test_crossing_when_endpoint_on_tripwire():
  """! Verify that endpoint landing exactly on the tripwire counts as a crossing. """
  tripwire = Tripwire(UUID, "tw", {"points": [[0, 0], [10, 0]]})
  result = getTripwireEvents({"tw": tripwire}, [(Point(5, 0), Point(5, -5))])
  assert len(result["tw"]) == 1
  assert result["tw"][0][0] == 0

# --- Length variations ---

def test_single_tripwire_single_object():
  """! Verify single tripwire with one crossing object. """
  tripwire = Tripwire(UUID, "tw", {"points": [[0, 0], [10, 0]]})
  result = getTripwireEvents({"tw": tripwire}, [(Point(5, 1), Point(5, -1))])
  assert len(result["tw"]) == 1
  assert result["tw"][0][0] == 0

def test_multiple_tripwires_multiple_objects():
  """! Verify detection with multiple tripwires and objects, one crossing both. """
  tw_h = Tripwire(UUID, "h", {"points": [[0, 0], [10, 0]]})
  tw_v = Tripwire(UUID, "v", {"points": [[5, -5], [5, 5]]})
  tripwires = {"h": tw_h, "v": tw_v}
  objects = [
    (Point(6, 1), Point(4, -1)),  # crosses both
    (Point(1, 5), Point(1, 4)),   # crosses neither
  ]
  result = getTripwireEvents(tripwires, objects)
  assert len(result["h"]) == 1
  assert result["h"][0][0] == 0
  assert len(result["v"]) == 1
  assert result["v"][0][0] == 0

# --- Empty inputs ---

def test_empty_object_list():
  """! Verify tripwires with no objects returns empty lists per key. """
  tripwire = Tripwire(UUID, "tw", {"points": [[0, 0], [10, 0]]})
  result = getTripwireEvents({"tw": tripwire}, [])
  assert result["tw"] == []

def test_empty_tripwire_dict():
  """! Verify empty tripwire dict returns empty result. """
  result = getTripwireEvents({}, [(Point(5, 1), Point(5, -1))])
  assert result == {}
