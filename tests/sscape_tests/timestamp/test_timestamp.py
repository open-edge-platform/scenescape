# Copyright (C) 2023 Intel Corporation
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
import numpy as np

from scene_common.timestamp import get_iso_time, get_epoch_time

@pytest.mark.parametrize("input_time, expected_time",
                        [(1678924070.942, "2023-03-15T23:47:50.942Z"),
                        (1127342123.122, "2005-09-21T22:35:23.122Z")])
def test_get_iso_time(input_time, expected_time):
  """! Verifies the output of timestamp.get_iso_time().

  @param    input_time       Input time as float
  @param    expected_time    Expected time as string in ISO format
  """
  iso_time = get_iso_time(input_time)
  assert iso_time == expected_time
  return

@pytest.mark.parametrize("input_time, expected_time",
                        [("2023-03-15T23:47:50.869Z", 1678924070.869),
                        ("2000-11-19T03:07:34.123Z", 974603254.123)])
def test_get_epoch_time(input_time, expected_time):
  """! Verifies the output of timestamp.get_epoch_time().

  @param    input_time       Input time as string in ISO format
  @param    expected_time    Expected time as float
  """
  epoch_time = get_epoch_time(input_time)
  assert np.isclose(epoch_time, expected_time, rtol=0.001)
  return

def test_restored_iso_time():
  """! Verifies restoring iso time from the output of get_epoch_time()
  using get_iso_time() """

  iso_time = get_iso_time()
  epoch_time = get_epoch_time(iso_time)
  restored_iso_time = get_iso_time(epoch_time)

  assert iso_time == restored_iso_time
  return

def test_restored_epoch_time():
  """! Verifies restoring epoch time from the output of get_iso_time()
  using get_epoch_time() """

  epoch_time = get_epoch_time()
  iso_time = get_iso_time(epoch_time)
  restored_epoch_time = get_epoch_time(iso_time)

  assert np.isclose(epoch_time, restored_epoch_time, rtol=0.001)
  return
