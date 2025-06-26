# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
