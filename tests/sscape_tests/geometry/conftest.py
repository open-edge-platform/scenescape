# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import pytest

import scene_common.geometry as geometry
import tests.common_test_utils as common

TEST_NAME = "NEX-T10454"
def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")

  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

# Class: Point

@pytest.fixture(scope="module")
def point2d():
  """! Creates a 2D Point class object as a fixture. """

  return geometry.Point(4., 6.)

@pytest.fixture(scope="module")
def point2d_polar():
  """! Creates a 2D polar Point class object as a fixture. """

  return geometry.Point(4., 6., polar=True)

@pytest.fixture(scope="module")
def point3d():
  """! Creates a 3D Point class object as a fixture. """

  return geometry.Point(4., 6., 8.)

@pytest.fixture(scope="module")
def point3d_polar():
  """! Creates a 3D polar Point class object as a fixture. """

  return geometry.Point(4., 6., 8., polar=True)

# Class: Size

@pytest.fixture(scope="module")
def size2d():
  """! Creates a 2D Size class object as a fixture. """

  return geometry.Size(1, 3)

@pytest.fixture(scope="module")
def size3d():
  """! Creates a 3D Size class object as a fixture. """

  return geometry.Size(1, 3, 5)

# Class: Line

@pytest.fixture(scope="module")
def line2d():
  """! Creates a 2D Line class object as a fixture. """

  start_point = geometry.Point(1., 3.)
  end_point = geometry.Point(2., 3.)

  return geometry.Line(start_point, end_point)

@pytest.fixture(scope="module")
def line3d():
  """! Creates a 3D Line class object as a fixture. """

  start_point = geometry.Point(1., 3., 5.)
  end_point = geometry.Point(2., 3., 5.)

  return geometry.Line(start_point, end_point)

# Class: Rectangle

@pytest.fixture(scope="module")
def rectangle():
  """! Creates a Rectangle class object as a fixture. """

  origin = geometry.Point(0., 0.)
  size = (2., 2.)
  return geometry.Rectangle(origin, size)

# Class: Region

@pytest.fixture(scope="module")
def region_poly():
  """! Creates a poly Region class object as a fixture. """

  info = [[2, 1], [5, 1], [5, 4], [2, 4]]
  uuid = "39bd9698-8603-43fb-9cb9-06d9a14e6a24"
  name = "test_poly"
  return geometry.Region(uuid, name, info)


@pytest.fixture(scope="module")
def region_circle():
  """! Creates a circle Region class object as a fixture. """

  info = {"area": "circle", "center": [5, 5], "radius": 10}
  uuid = "39bd9698-8603-43fb-9cb9-06d9a14e6a24"
  name = "test_circle"
  return geometry.Region(uuid, name, info)
