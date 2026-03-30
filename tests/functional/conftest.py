#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import numpy as np

@pytest.fixture
def obj_location(request):
  """! Moving object locations used in test_roi_mqtt.py.
  @return   location    Object location.
  """
  step = 0.02
  opposite = np.arange(-0.5, 0.6, step)
  across = np.flip(opposite)[2:]
  location = np.concatenate((opposite, across))

  gap = np.array([abs(x - y) for x, y in zip(location[:-1], location[1:])])
  too_large = np.where(np.isclose(gap, step) == False)
  if len(too_large[0]):
    np.delete(location, too_large[0])
  return location

@pytest.fixture
def objData():
  """! Moving object data used in test_roi_mqtt.py
  @return   location    Object data.
  """
  jdata = {
    "id": "camera1",
    "objects": {},
    "rate": 9.8
  }
  obj = {
    "id": 1,
    "category": "person",
    "bounding_box": {
      "x": 0.56,
      "y": 0.0,
      "width": 0.24,
      "height": 0.49
    }
  }
  jdata['objects']['person'] = [obj]
  return jdata

def pytest_runtest_makereport(item, call):
  if call.when == "call":
    if hasattr(item, 'callspec') and 'test_name' in item.callspec.params:
      test_name = item.callspec.params['test_name']
      item._nodeid = f"{item.nodeid}\n {test_name}"
