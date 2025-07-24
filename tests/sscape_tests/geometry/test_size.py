# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
import numpy as np

from scene_common import geometry

@pytest.mark.parametrize("width, height, depth, expected_output",
                        [(None, None, None, "Passed arguments do not make a size"),
                        (1, 2, None, (1, 2, None)),
                        (1, 2, 3, (1, 2, 3))])

def test_size_init(width, height, depth, expected_output):
  """! Verifies the output of 'geometry.Size.__init__()' method. """

  try:
    if depth is None:
      size = geometry.Size(width, height)
    else:
      size = geometry.Size(width, height, depth)
    assert size.width == expected_output[0] and size.height == expected_output[1]
    if expected_output[2] is not None:
      assert size.depth == expected_output[2] and size.is3D

  except TypeError as error:
    pass

  return

def test_depth(size3d):
  """! Verifies the output of 'geometry.Size.depth' property. """

  expected_result = 5
  depth = size3d.depth

  assert depth == expected_result
  return

def test_asNumpy(size2d):
  """! Verifies the output of 'geometry.Size.asNumpy' property. """

  expected_result = np.float64([size2d.width, size2d.height])
  size_asnumpy = size2d.asNumpy

  assert np.array_equal(size_asnumpy, expected_result, equal_nan=True)
  return

@pytest.mark.parametrize("fixture, expected_result", [("size2d", False), ("size3d", True)])
def test_is3D(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Size.is3D' property. """

  size = request.getfixturevalue(fixture)
  assert size.is3D == expected_result

  return

@pytest.mark.parametrize("fixture, expected_result",
                        [("size2d", "(1.000, 3.000)"),
                        ("size3d", "(1.000, 3.000, 5.000)")])

def test_log(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Size.log' property. """

  size = request.getfixturevalue(fixture)
  assert size.log == expected_result

  return

@pytest.mark.parametrize("fixture, expected_result",
                        [("size2d", "Size: (1.000, 3.000)"),
                        ("size3d", "Size: (1.000, 3.000, 5.000)")])

def test_repr(fixture, expected_result, request):
  """! Verifies the output of 'geometry.Size.__repr__()' dunder method. """

  size = request.getfixturevalue(fixture)
  assert repr(size) == expected_result

  return
