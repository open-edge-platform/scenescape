#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
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
  parser.addoption("--expect_exceed_max", default="false",
                   help="Whether unique count is expected to exceed max (true/false)")

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
    'expect_exceed_max': request.config.getoption('--expect_exceed_max'),
  }

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

@pytest.fixture(scope="function")
def rest(params):
  client = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert client.authenticate(params['user'], params['password'])
  return client

@pytest.fixture(scope="function")
def scene_uid(rest, params):
  name = params['scene_name']
  res = rest.getScenes({'name': name})
  scenes = res.get('results', []) if isinstance(res, dict) else []
  assert scenes, f"Scene '{name}' not found"
  return scenes[0]['uid']

@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
  file_name = Path(config.option.file_or_dir[0]).stem
  config.option.htmlpath = os.getcwd() + '/tests/functional/reports/test_reports/' + file_name + ".html"

def pytest_runtest_makereport(item, call):
  if call.when == "call":
    if hasattr(item, 'callspec') and 'test_name' in item.callspec.params:
      test_name = item.callspec.params['test_name']
      item._nodeid = f"{item.nodeid}\n {test_name}"

@pytest.fixture(scope="function")
def _env_matrix_setup(request):
  """Override of root no-op fixture for functional tests.

  When --env-profiles is used, pytest_generate_tests parametrizes this
  fixture with a profile-specific FuncTestSpec.
  This fixture then injects the spec into the node before scenescape_env
  reads it, so Docker Compose starts the correct profile.
  """
  if hasattr(request, 'param'):
    request.node._scenescape_spec = request.param
    if request.param.test_name:
      request.node._scenescape_test_name = request.param.test_name


def pytest_generate_tests(metafunc):
  """Parametrize tests across profiles supplied via --env-profiles.

  Only activates when the --env-profiles CLI option is provided

  Tests run once per profile, each with a distinct Docker Compose environment.
  Profile names must match entries in tests.utils.profiles.PROFILE_REGISTRY.
  """
  spec = getattr(metafunc.module, 'SCENESCAPE_SPEC', None)
  if spec is None:
    return

  env_profiles_arg = metafunc.config.getoption("env_profiles", default=None)
  if not env_profiles_arg:
    return

  from dataclasses import replace
  from tests.utils.profiles import PROFILE_REGISTRY

  profile_names = [name.strip() for name in env_profiles_arg.split(",") if name.strip()]
  unknown = [n for n in profile_names if n not in PROFILE_REGISTRY]
  if unknown:
    raise ValueError(
      f"Unknown profile(s) in --env-profiles: {', '.join(unknown)}. "
      f"Valid profiles: {', '.join(sorted(PROFILE_REGISTRY))}"
    )

  # SCENESCAPE_ENV_MATRIX: dict mapping profile name -> NEX ID for allowed profiles.
  # Tests not declaring it run against all requested profiles.
  matrix = getattr(metafunc.module, 'SCENESCAPE_ENV_MATRIX', None)

  params = []
  for profile_name in profile_names:
    profile = PROFILE_REGISTRY[profile_name]
    if matrix is not None and profile_name not in matrix:
      # Profile not supported by this test — parametrize as skipped so it
      # appears in the report but no environment is targeted.
      params.append(pytest.param(
        replace(spec, profile=profile),
        marks=pytest.mark.skip(reason=f"Test not designed for profile '{profile_name}'"),
      ))
    else:
      nex_id = matrix[profile_name] if matrix is not None else ""
      params.append(replace(spec, profile=profile, test_name=nex_id))

  if '_env_matrix_setup' not in metafunc.fixturenames:
    metafunc.fixturenames.append('_env_matrix_setup')

  metafunc.parametrize(
    "_env_matrix_setup",
    params,
    ids=profile_names,
    indirect=True,
  )
