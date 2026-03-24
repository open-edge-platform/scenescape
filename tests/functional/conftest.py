#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import logging
from datetime import datetime
from pathlib import Path
import numpy as np

def pytest_addoption(parser):
  parser.addoption("--user", required=True, help="user to log into REST server")
  parser.addoption("--password", required=True, help="password to log into REST server")
  parser.addoption("--auth", default="/run/secrets/controller.auth",
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
  parser.addoption("--visibility_topic", default="regulated",
                   help="Visibility policy: regulated, unregulated, none")

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

def pytest_runtest_makereport(item, call):
  if call.when == "call":
    if hasattr(item, 'callspec') and 'test_name' in item.callspec.params:
      test_name = item.callspec.params['test_name']
      item._nodeid = f"{item.nodeid}\n {test_name}"

@pytest.fixture
def test_logger(request):
  """Per-test logger with file and console output."""

  logger = logging.getLogger(request.node.name)
  logger.setLevel(logging.DEBUG)

  # Avoid duplicate handlers if reused
  if logger.handlers:
    return logger

  log_dir = os.path.join(os.getcwd(), "tests", "functional", "logs")
  os.makedirs(log_dir, exist_ok=True)

  test_name = request.node.name.replace("/", "_").replace(" ", "_")
  timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

  log_file = os.path.join(log_dir, f"{test_name}_{timestamp}.log")
  formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

  console_handler = logging.StreamHandler()
  console_handler.setLevel(logging.INFO)
  console_handler.setFormatter(formatter)
  logger.addHandler(console_handler)

  file_handler = logging.FileHandler(log_file, mode="w")
  file_handler.setLevel(logging.DEBUG)
  file_handler.setFormatter(formatter)
  logger.addHandler(file_handler)

  logger.info(
    "Logger initialized. Logs will be written to console and %s",
    log_file)

  yield logger

  # Cleanup
  logger.removeHandler(console_handler)
  logger.removeHandler(file_handler)
