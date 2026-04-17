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
    if hasattr(item, 'callspec') and '_env_matrix_setup' in item.callspec.params:
      spec = item.callspec.params['_env_matrix_setup']
      test_name = getattr(spec, 'test_name', '')
      if test_name:
        item._nodeid = f"{item.nodeid}\n {test_name}"


@pytest.fixture
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

  env_profiles_arg = metafunc.config.getoption("--env-profiles", default=None)
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
      # appears in the report but no environment is started.
      params.append(pytest.param(
        replace(spec, profile=profile),
        marks=pytest.mark.skip(reason=f"Test not designed for profile '{profile_name}'"),
      ))
    else:
      nex_id = matrix[profile_name] if matrix is not None else ""
      params.append(replace(spec, profile=profile, test_name=nex_id))

  metafunc.parametrize(
    "_env_matrix_setup",
    params,
    ids=profile_names,
    indirect=True,
  )

