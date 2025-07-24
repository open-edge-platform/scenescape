# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
import numpy as np

import scene_common.geometry as geometry

@pytest.mark.parametrize("point1, point2, relative, expected_output",
      [(1, None, None, "point1 is not a Point"),
      (geometry.Point(1., 2.), 1, None, "point2 is not a Point"),
      (geometry.Point(1., 2.), geometry.Point(5., 6., 7.), None, "Cannot mix 2D and 3D points"),
      (geometry.Point(1., 2.), geometry.Point(5., 6.), True, [(1, 2, None), (6, 8, None)])])

def test_line_init(point1, point2, relative, expected_output):
  """! Verifies the output of 'geometry.Line.__init__()' method. """

  try:
    line = geometry.Line(point1, point2, relative)
    assert line.origin.x == expected_output[0][0]
    assert line.origin.y == expected_output[0][1]
    assert line.end.x == expected_output[1][0]
    assert line.end.y == expected_output[1][1]

  except TypeError as error:
    #assert expected_output in str(error)
    pass

  except ValueError as error:
    assert expected_output in str(error)

  return

@pytest.mark.parametrize("first_line, second_line, expected_output",
  [("line2d", "line3d", "Cannot mix 2D and 3D lines"),
  ("line2d", geometry.Line(geometry.Point(3., 5.), geometry.Point(5., 7.)), (True, (1., 3.))),
  ("line2d", geometry.Line(geometry.Point(1., 3.), geometry.Point(2., 3.)), (False, (0., 0.))),
  ("line3d", geometry.Line(geometry.Point(1., 3., 5.), geometry.Point(2., 3., 5.)), (False, (0.,0.)))])

def test_intersection(first_line, second_line, expected_output, request):
  """! Verifies the output of 'geometry.Line.intersection()' method. """

  if isinstance(first_line, str):
    first_line = request.getfixturevalue(first_line)

  if isinstance(second_line, str):
    second_line = request.getfixturevalue(second_line)

  try:
    intersection = first_line.intersection(second_line)
    assert repr(intersection) == repr(expected_output)

  except ValueError as error:
    assert expected_output in str(error)

  return

@pytest.mark.parametrize("fixture, point, expected_output",
        [("line2d", geometry.Point(1., 3., 5.), "Cannot mix 2D and 3D coordinates"),
        ("line2d", geometry.Point(1., 3.), True),
        ("line2d", geometry.Point(7., 8.), False)])

def test_isPointOnLine(fixture, point, expected_output, request):
  """! Verifies the output of 'geometry.Line.isPointOnLine()' method. """

  line = request.getfixturevalue(fixture)

  try:
    is_on_line = line.isPointOnLine(point)
    assert is_on_line == expected_output

  except ValueError as error:
    assert expected_output in str(error)

  return

@pytest.mark.parametrize("first_line, second_line, expected_output",
  [("line2d", "line3d", "Cannot mix 2D and 3D lines"),
  (geometry.Line(geometry.Point(1., 3.), geometry.Point(2., -3.)), "line2d", 80.53767779197437),
  ("line2d", geometry.Line(geometry.Point(1., 3.), geometry.Point(2., -3.)), 80.53767779197437)])

def test_angleDiff(first_line, second_line, expected_output, request):
  """! Verifies the output of 'geometry.Line.angleDiff()' method. """

  if isinstance(first_line, str):
    first_line = request.getfixturevalue(first_line)

  if isinstance(second_line, str):
    second_line = request.getfixturevalue(second_line)

  try:
    angleDiff = first_line.angleDiff(second_line)
    assert np.isclose(angleDiff, expected_output, rtol=1e-03)

  except ValueError as error:
    assert expected_output in str(error)

  return

def test_repr(line2d):
  """! Verifies the output of 'geometry.Line.__repr__()' dunder method. """

  expected_output = "Line: Point: (1.000, 3.000) Point: (2.000, 3.000)"
  assert repr(line2d) == expected_output

  return

def test_origin(line2d):
  """! Verifies the output of 'geometry.Line.origin' property. """

  expected_output = geometry.Point(1, 3)
  assert line2d.origin == expected_output

  return

def test_x1(line2d):
  """! Verifies the output of 'geometry.Line.x1' property. """

  expected_output = 1
  assert line2d.x1 == expected_output

  return

def test_y1(line2d):
  """! Verifies the output of 'geometry.Line.y1' property. """

  expected_output = 3
  assert line2d.y1 == expected_output

  return

def test_z1(line3d):
  """! Verifies the output of 'geometry.Line.z1' property. """

  expected_output = 5
  assert line3d.z1 == expected_output

  return

def test_x2(line2d):
  """! Verifies the output of 'geometry.Line.x2' property. """

  expected_output = 2
  assert line2d.x2 == expected_output

  return

def test_y2(line2d):
  """! Verifies the output of 'geometry.Line.y2' property. """

  expected_output = 3
  assert line2d.y2 == expected_output

  return

def test_z2(line3d):
  """! Verifies the output of 'geometry.Line.z2' property. """

  expected_output = 5
  assert line3d.z2 == expected_output

  return

def test_inclination(line3d):
  """! Verifies the output of 'geometry.Line.inclination' property. """

  expected_output = 0
  assert line3d.inclination == expected_output

  return
