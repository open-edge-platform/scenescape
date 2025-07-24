# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import pytest
from collections import deque
import numpy as np

import scene_common.geometry as geometry

def compare_points_cartesian( pt1, pt2 ):
  assert pt1.x == pt2[0]
  assert pt1.y == pt2[1]
  assert pt1.is3D == (pt2[2] is not None)
  if pt1.is3D :
    assert pt1.z == pt2[2]
  return

def compare_points_polar( pt1, pt2 ):
  assert pt1.radius == pt2[0]
  assert pt1.azimuth == pt2[1]
  assert pt1.is3D == (pt2[2] is not None)
  if pt1.is3D :
    assert pt1.inclination == pt2[2]
  return

@pytest.mark.parametrize(
  "args, polar, expected_output",
  [([None, None, None], None, "No coordinates"),
    ([4., 6., None], None, (4, 6, None)),
    ([4., 6., None], True, (4, 6, None)),
    ([5., 7., 11.], None, (5, 7, 11)),
    ([5., 7., 11.], True, (5, 7, 11)),
    ([13., 17., 29.], True, (13, 17, 29))])

def test_point_init(args, polar, expected_output):
  """! Verifies the output of 'geometry.Point.__init__()' method. """

  try:
    point_args = [args[0], args[1]]
    if args[2] is not None:
      point_args.append(args[2])
    point = geometry.Point(point_args, polar)
    if polar:
      compare_points_polar( point, expected_output )
    else:
      compare_points_cartesian( point, expected_output )

  except TypeError as error:
    pass

  return

@pytest.mark.parametrize("fixture, tuple, expected_result",
                        [("point2d", (2., 2.), (5.0, 7.0, None)),
                         ("point3d", (2., 2., 2.), (5.0, 7.0, 9.0))])

def test_midpoint(fixture, tuple, expected_result, request):
  """! Verifies the output of 'geometry.Point.midpoint()' method. """

  first_point = request.getfixturevalue(fixture)
  second_point = first_point + tuple
  result = first_point.midpoint(second_point)

  compare_points_cartesian( result, expected_result )
  return

def test_midpoint_typeerror(point2d, point3d):
  """! Verifies the output of 'geometry.Point.midpoint()' type error. """

  expected_result = "Cannot mix 3D and 2D points"
  try:
    _ = point2d.midpoint(point3d)
    assert False
  except ValueError as error:
    assert expected_result in str(error)

  return

@pytest.mark.parametrize("fixture, expected_result",
                        [("point2d", "Cannot get Z from 2D point"),
                         ("point3d", 8)])

def test_z(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Point.z' property. """

  point = request.getfixturevalue(fixture)

  try:
    z = point.z
    assert z == expected_result
  except ValueError as error:
    assert expected_result in str(error)

  return

@pytest.mark.parametrize("fixture, expected_result",
                        [("point2d", 7.211102550927978),
                         ("point3d", 10.770329614269007)])

def test_radius(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Point.radius' property. """

  point = request.getfixturevalue(fixture)
  assert np.isclose(point.radius, expected_result, rtol=1e-03)

  return

@pytest.mark.parametrize("fixture, tuple, expected_result",
                        [("point2d", (-5, -7), "Cannot get inclination from 2D point"),
                         ("point3d", (-5, -7, -9), 324.73561031724535)])

def test_inclination(fixture, tuple, expected_result, request):
  """! Verifies the output of 'geometry.Point.inclination' property. """

  point = request.getfixturevalue(fixture)
  point = point + tuple

  try:
    inclination = point.inclination
    assert np.isclose(inclination, expected_result, rtol=1e-03)

  except ValueError as error:
    assert expected_result in str(error)

  return

@pytest.mark.parametrize("point, expected_result",
                        [("point2d", (4, 6)),
                         (geometry.Point(4.5, 6.9), (4, 6)),
                         ("point3d", "Cannot get cv from 3D point")])

def test_cv(point, expected_result, request):
  """! Verifies the output of 'geometry.Point.cv' property. """

  if isinstance(point, str):
    point = request.getfixturevalue(point)

  try:
    cv = point.cv
    assert cv == expected_result
  except ValueError as error:
    assert expected_result in str(error)

  return

@pytest.mark.parametrize("fixture, expected_result",
        [("point2d_polar", (3.978087581473093, 0.4181138530706139, None)),
          ("point3d", (4, 6, 8)),
          ("point3d_polar", (3.978087581473093, 0.4140447977943335, 0.5536427846043374))])

def test_asCartesian(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Point.asCartesian' property. """

  point = request.getfixturevalue(fixture)

  cartesian_point = point.asCartesian
  cartesian_array = [cartesian_point.x, cartesian_point.y]
  if cartesian_point.is3D:
    cartesian_array.append(cartesian_point.z)
  else:
    cartesian_array.append(np.nan)
  assert np.allclose(np.array(cartesian_array, dtype=float),
                              np.array(expected_result, dtype=float),
                              rtol=1e-03,
                              equal_nan=True)


  return

@pytest.mark.parametrize("fixture, expected_result",
        [("point2d", (7.211102550927978, 56.309932474020215, None)),
          ("point3d", (10.770329614269007, 56.309932474020215, 47.96888622580271)),
          ("point3d_polar", (4, 6, 8))])

def test_asPolar(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Point.asPolar' property. """

  point = request.getfixturevalue(fixture)

  polar_point = point.asPolar

  polar_array = [polar_point.radius, polar_point.azimuth]
  if polar_point.is3D:
    polar_array.append(polar_point.inclination)
  else:
    polar_array.append(np.nan)

  assert np.allclose(np.array(polar_array, dtype=float),
                              np.array(expected_result, dtype=float),
                              rtol=1e-03,
                              equal_nan=True)

  return

@pytest.mark.parametrize("fixture",
                        [("point2d"), ("point2d_polar"), ("point3d"), ("point3d_polar")])
def test_asNumpyCartesian(fixture, request):
  """! Verifies the output of 'geometry.Point.asNumpyCartesian' property. """

  point = request.getfixturevalue(fixture)
  numpy_cartesian_point = point.asNumpyCartesian

  if point.is3D:
    assert (numpy_cartesian_point ==  np.float64((point.x, point.y, point.z))).all()
  else:
    assert (numpy_cartesian_point ==  np.float64((point.x, point.y))).all()

  return

@pytest.mark.parametrize("fixture, expected_result",
                        [("point2d", "(4.000, 6.000)"),
                         ("point3d", "(4.000, 6.000, 8.000)"),
                         ("point3d_polar", "P(4.000, 6.000, 8.000)")])

def test_log(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Point.log' property. """

  point = request.getfixturevalue(fixture)
  assert point.log == expected_result

  return

def test_as2Dxz(point3d):
  """! Verifies the output of 'geometry.Point.as2Dxz' property. """

  new_point = point3d.as2Dxz
  assert new_point.x == point3d.x
  assert new_point.y == point3d.z

  return

def test_as2Dyz(point3d):
  """! Verifies the output of 'geometry.Point.as2Dyz' property. """

  new_point = point3d.as2Dyz
  assert new_point.x == point3d.y
  assert new_point.y == point3d.z

  return

@pytest.mark.parametrize("fixture, tuple, expected_result",
                        [("point2d", (1., 1.), (9.0, 13.0, None)),
                         ("point2d_polar", (1, 1), "Cannot do Cartesian math on polar points")])

def test_add(fixture, tuple, expected_result, request):
  """! Verifies the output of 'geometry.Point.__add__()' dunder method. """

  point = request.getfixturevalue(fixture)

  try:
    second_point = point + tuple
    result = point + second_point
    compare_points_cartesian( result, expected_result )
  except ValueError as error:
    assert expected_result in str(error)

  return

@pytest.mark.parametrize("fixture, tuple, expected_result",
                        [("point2d", (-1., -1.), (-1.0, -1.0, None)),
                         ("point2d_polar", (-1., -1.), "Cannot do Cartesian math on polar points")])

def test_sub(fixture, tuple, expected_result, request):
  """! Verifies the output of 'geometry.Point.__sub__()' dunder method. """

  point = request.getfixturevalue(fixture)

  try:
    second_point = point - tuple
    result = point - second_point
    compare_points_cartesian( result, expected_result )
  except ValueError as error:
    assert expected_result in str(error)
  return

@pytest.mark.parametrize("fixture, tuple, expected_result",
                        [("point2d", (1., 1.), False),
                        ("point2d", (0., 0.), True)])

def test_equal(fixture, tuple, expected_result, request):
  """! Verifies the output of 'geometry.Point.__eq__()' dunder method. """

  point = request.getfixturevalue(fixture)
  second_point = point + tuple

  try:
    result = point == second_point
    assert result == expected_result
  except ValueError as error:
    assert expected_result in str(error)
  return
