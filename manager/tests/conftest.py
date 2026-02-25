#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import sys
from pathlib import Path
from scene_common.rest_client import RESTClient

repo_root=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from tests.common_test_utils import record_test_result

def pytest_report_teststatus(report, config):
  if report.when == "call":
    # Disable default "PASSED"
    return report.outcome, "", ""

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

@pytest.fixture(scope="session")
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
  config.option.htmlpath = os.getcwd() + '/tests/reports/test_reports/' + file_name + ".html"
  # Register marker for test names
  config.addinivalue_line("markers", "test_name(name): sets the XML test name attribute")

@pytest.fixture(scope="session")
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

@pytest.fixture(autouse=True)
def record_test_name(request, record_xml_attribute):
  """Record test name from marker if provided; otherwise do nothing."""
  marker = request.node.get_closest_marker("test_name")
  if marker and marker.args:
    record_xml_attribute("name", marker.args[0])

@pytest.fixture
def result_recorder(request):
  """Provides .success(); records exit code with test name on teardown."""
  marker = request.node.get_closest_marker("test_name")
  test_name = (marker.args[0] if marker and marker.args
    else getattr(request.node.module, "TEST_NAME", request.node.name))

  class Result:
    exit_code = 1
    def success(self):
      self.exit_code = 0

  r = Result()
  try:
    yield r
  finally:
    record_test_result(test_name, r.exit_code)
