#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
