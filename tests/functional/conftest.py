#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import pytest
from pathlib import Path
import numpy as np

def pytest_addoption(parser):
  parser.addoption("--user", required=True, help="user to log into REST server")
  parser.addoption("--password", required=True, help="password to log into REST server")
  parser.addoption("--auth", default="/run/secrets/percebro.auth",
                   help="user:password or JSON file for MQTT authentication")
  parser.addoption("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                   help="path to ca certificate")
  parser.addoption("--broker_url", default="broker.scenescape.intel.com",
                   help="hostname or IP of MQTT broker")
  parser.addoption("--broker_port", default="1883", type=int, help="Port of MQTT broker")
  parser.addoption("--weburl", default="https://web.scenescape.intel.com",
                   help="Web URL of the server")
  parser.addoption("--resturl", default="https://web.scenescape.intel.com/api/v1",
                   help="URL of REST server")
  parser.addoption("--scene_name", default="Demo",
                   help="name of scene to test against")

@pytest.fixture
def params(request):
  return {
    'user': request.config.getoption('--user'),
    'password': request.config.getoption('--password'),

    'auth': request.config.getoption('--auth'),
    'rootcert': request.config.getoption('--rootcert'),

    'broker_url': request.config.getoption('--broker_url'),
    'broker_port': request.config.getoption('--broker_port'),

    'weburl': request.config.getoption('--weburl'),
    'resturl': request.config.getoption('--resturl'),

    'scene_name': request.config.getoption('--scene_name'),
  }

@pytest.fixture
def obj_location(request):
  """! Moving object locations used in tc_roi_mqtt.py.
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
  """! Moving object data used in tc_roi_mqtt.py
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

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
  file_name = Path(config.option.file_or_dir[0]).stem
  config.option.htmlpath = os.getcwd() + '/tests/functional/reports/test_reports/' + file_name + ".html"
