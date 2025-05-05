#!/usr/bin/env python3

# Copyright (C) 2021 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import numpy as np
import pytest

from percebro import detector

random_array = np.random.randint(255, size=(5, 10))

# Tests for NumpyEncoder class

@pytest.mark.parametrize("object, expected_output",
                        [(random_array, random_array.tolist()),
                        ([1, 2, 3], None)])
def test_default(object, expected_output):
  """! Verifies the output of 'detector.NumpyEncoder.default()' method.

  @param    object            An array of detected objects
  @param    expected_output   Expected output
  """

  numpy_encoder = detector.NumpyEncoder()

  try:
    original_output = numpy_encoder.default(object)
    assert original_output == expected_output
  except TypeError:
    assert type(object) != np.ndarray

  return
