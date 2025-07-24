# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest

from scene_common import geometry

@pytest.mark.parametrize("origin, size, opposite, expected_origin, expected_size",
      [(None, None, None, None, None),
      ({'x': 0, 'y': 0, 'width': 2, 'height': 2}, None, None, (0, 0, None), (2, 2, None)),
      (geometry.Point(0., 0.), (2., 2.), None, (0, 0, None), (2, 2, None)),
      (geometry.Point(0., 0.), [2., 2.], None, (0, 0, None), (2, 2, None)),
      (geometry.Point(0., 0.), None, geometry.Point(2., 2.), (0., 0., None), (2., 2., None))])

def test_rectangle_init(origin, size, opposite, expected_origin, expected_size):
  """! Verifies the output of 'geometry.Rectangle.__init__()' method. """

  rectangle = None

  if origin:
    if isinstance(origin, dict):
      rectangle = geometry.Rectangle(origin)
    elif opposite is not None:
      rectangle = geometry.Rectangle(origin, opposite)
    else:
      rectangle = geometry.Rectangle(origin, size)
    assert rectangle.origin.x == expected_origin[0]
    assert rectangle.origin.y == expected_origin[1]
    assert rectangle.size.width == expected_size[0] and rectangle.size.height == expected_size[1]
  else:
    assert not hasattr(rectangle, 'origin') and not hasattr(rectangle, 'size')

  return

def test_x1(rectangle):
  """! Verifies the output of 'geometry.Rectangle.x1' property. """

  expected_result = 0
  assert rectangle.x1 == expected_result

  return

def test_y1(rectangle):
  """! Verifies the output of 'geometry.Rectangle.y1' property. """

  expected_result = 0
  assert rectangle.y1 == expected_result

  return

def test_area(rectangle):
  """! Verifies the output of 'geometry.Rectangle.area' property. """

  expected_result = 4
  assert rectangle.area == expected_result

  return

@pytest.mark.parametrize("rectangle_obj, expected_result",
                        [("rectangle", ((0, 0), (2, 2))),
                         (geometry.Rectangle(geometry.Point(3.3, 3.8), (5.7, 5.1)), ((3, 3), (9, 8)))])

def test_cv(rectangle_obj, expected_result, request):
  """! Verifies the output of 'geometry.Rectangle.cv' property. """

  if isinstance(rectangle_obj, str):
    rectangle_obj = request.getfixturevalue(rectangle_obj)

  assert rectangle_obj.cv == expected_result

  return

@pytest.mark.parametrize("first_rectangle, second_rectangle, expected_output",
  [("rectangle", geometry.Rectangle(geometry.Point(1., 1.), (3., 3.)), geometry.Rectangle(geometry.Point(1., 1.), (1., 1.))),
  ("rectangle", geometry.Rectangle(geometry.Point(3., 3.), (5., 5.)), None)])

def test_intersection(first_rectangle, second_rectangle, expected_output, request):
  """! Verifies the output of 'geometry.Rectangle.intersection()' method. """

  if isinstance(first_rectangle, str):
    first_rectangle = request.getfixturevalue(first_rectangle)

  if isinstance(second_rectangle, str):
    second_rectangle = request.getfixturevalue(second_rectangle)

  intersection = first_rectangle.intersection(second_rectangle)
  if expected_output is None:
    assert intersection.height == 0 and intersection.width == 0
  else:
    assert repr(intersection) == repr(expected_output)

  return

def test_offset(rectangle):
  """! Verifies the output of 'geometry.Rectangle.offset()' method. """

  point = geometry.Point(1., 1.)
  expected_result = geometry.Rectangle(geometry.Point(1., 1.), (2., 2.))

  assert repr(rectangle.offset(point)) == repr(expected_result)
  return
