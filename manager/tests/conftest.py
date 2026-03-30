#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

import pytest
from scene_common.rest_client import RESTClient

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
  sys.path.insert(0, str(repo_root))

from tests.common_test_utils import record_test_result

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
