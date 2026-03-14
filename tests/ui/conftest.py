#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import pytest
from pathlib import Path

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
  parser.addoption(
    "--analytics-only",
    action="store_true",
    default=False,
    help="Enable analytics-only mode for tests (tracker disabled)"
  )

@pytest.fixture
def params(request):
  params = {
    'user': request.config.getoption('--user'),
    'password': request.config.getoption('--password'),

    'auth': request.config.getoption('--auth'),
    'rootcert': request.config.getoption('--rootcert'),

    'broker_url': request.config.getoption('--broker_url'),
    'broker_port': request.config.getoption('--broker_port'),

    'weburl': request.config.getoption('--weburl'),
    'resturl': request.config.getoption('--resturl'),
  }
  if params['user'] is None or params['password'] is None:
    pytest.skip("Test requires --user <USER> and --password <PASSWORD>")
  return params

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
  file_name = Path(config.option.file_or_dir[0]).stem
  config.option.htmlpath = os.getcwd() + '/tests/ui/reports/test_reports/' + file_name + ".html"
  
# Ensure controller module is importable from controller/src
controller_src = Path(__file__).resolve().parents[2] / 'controller' / 'src'
sys.path.insert(0, str(controller_src))

from controller.controller_mode import ControllerMode

@pytest.fixture(scope='session', autouse=True)
def initialize_controller_mode(request):
  """
  Initialize ControllerMode before any tests run.

  This fixture is automatically used by all tests under the tests/ directory.
  It initializes the ControllerMode singleton to prevent "not initialized" warnings.

  Tests default to non-analytics mode (tracking enabled) unless overridden
  by the --analytics-only command-line option.
  """
  # Check if --analytics-only option exists; default to False if not provided
  analytics_only = request.config.getoption('analytics_only', default=False)
  ControllerMode.initialize(analytics_only=analytics_only)
  yield
  # Clean up after all tests complete
  ControllerMode.reset()
