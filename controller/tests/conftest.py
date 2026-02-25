#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import sys
from pathlib import Path
import numpy as np

# Add controller/src to path FIRST so controller module imports work correctly
controller_src = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(controller_src))

# Add repository root to path so 'tests' module can be imported
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from controller.controller_mode import ControllerMode

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
  parser.addoption("--analytics-only", action="store_true",
                   help="Enable analytics-only mode for tests")

@pytest.fixture(scope='session', autouse=True)
def initialize_controller_mode(request):
  """Initialize ControllerMode before any tests run."""
  analytics_only = request.config.getoption('analytics_only', default=False)
  ControllerMode.initialize(analytics_only=analytics_only)
  yield
  ControllerMode.reset()

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

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
  file_name = Path(config.option.file_or_dir[0]).stem
  config.option.htmlpath = os.getcwd() + '/tests/functional/reports/test_reports/' + file_name + ".html"
