#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
import logging
from pathlib import Path

import pytest
import numpy as np
from scene_common.rest_client import RESTClient

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
  sys.path.insert(0, str(repo_root))

logger = logging.getLogger(__name__)

DEMO_SCENE_NAME = "Demo"

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

@pytest.fixture
def rest(params):
  client = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert client.authenticate(params['user'], params['password'])
  return client

@pytest.fixture
def scene_uid(rest, params):
  name = params['scene_name']
  res = rest.getScenes({'name': name})
  scenes = res.get('results', []) if isinstance(res, dict) else []
  assert scenes, f"Scene '{name}' not found"
  return scenes[0]['uid']



