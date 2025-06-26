# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest

from scene_common import geometry

@pytest.mark.parametrize("info",
                [({"area": "poly", "points": [[2, 1], [5, 1], [5, 4], [2, 4]]}),
                ([[2, 1], [5, 1], [5, 4], [2, 4]]),
                ({"area": "circle", "center": [5, 5], "radius": 10})])

@pytest.mark.parametrize("uuid", ["39bd9698-8603-43fb-9cb9-06d9a14e6a24"])

@pytest.mark.parametrize("name", ["test_poly", "01234", "#$Demo13"])

def test_region_init(uuid, name, info):
  """! Verifies the output of 'geometry.Region.__init__()' method. """

  region = geometry.Region(uuid, name, info)

  assert region.boundingBox
  assert isinstance(region.boundingBox, geometry.Rectangle)

  return

@pytest.mark.parametrize("uuid, name, info, point, expected_result",
      [("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "test_region",  [[2, 1], [5, 1], [5, 4], [2, 4]], geometry.Point(1, 2), False),
      ("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "test_region",  [[2, 1], [5, 1], [5, 4], [2, 4]], geometry.Point(3, 3), True),
      ("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "test_region",  {"area": "circle", "center": [5, 5], "radius": 10}, geometry.Point(5, 5), True),
      ("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "test_region",  {"area": "circle", "center": [5, 5], "radius": 10}, geometry.Point(10, 11), True),
      ("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "test_region",  {"area": "circle", "center": [5, 5], "radius": 10}, geometry.Point(15, 15), False)])

def test_isPointWithin(uuid, info, name, point, expected_result):
  """! Verifies the output of 'geometry.Region.isPointWithin()' method. """

  region = geometry.Region(uuid, name, info)
  is_within = region.isPointWithin(point)
  assert is_within == expected_result

  return

@pytest.mark.parametrize("region, expected_result",
    [("region_poly", [(2, 1), (5, 1), (5, 4), (2, 4)]),
      (geometry.Region("39bd9698-8603-43fb-9cb9-06d9a14e6a24", "region_poly", [(2.3, 1.5), (5.1, 1.0), (5.2, 4.1), (2.7, 4.9)]), [(2, 1), (5, 1), (5, 4), (2, 4)])])

def test_cv(region, expected_result, request):
  """! Verifies the output of 'geometry.Region.cv' property. """

  if isinstance(region, str):
    region = request.getfixturevalue(region)

  assert region.cv == expected_result

  return

@pytest.mark.parametrize("fixture, expected_result",
                        [("region_poly", [[2, 1], [5, 1], [5, 4], [2, 4]]),
                        ("region_circle", None)])

def test_coordinates(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Region.coordinates' property. """

  region = request.getfixturevalue(fixture)

  if region.coordinates:
    for original, expected in zip(region.coordinates, expected_result):
      assert list(original) == expected
  else:
    assert region.coordinates == expected_result

  return

def test_repr(region_poly):
  """! Verifies the output of 'geometry.Region.__repr__()' dunder method. """

  expected_result = "Region: person:0 vehicle:0"
  assert expected_result in repr(region_poly)

  return
