#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
unit test wrappers.

Each entry maps to an existing Makefile target in tests/Makefile.sscape.
Standalone unit tests run locally from the venv.
Compose-based unit tests require a compose stack for service dependencies.
"""

import pytest

from conftest import FuncTestSpec, UnitTestSpec
from utils.profiles import MARKERLESS


# ---------------------------------------------------------------------------
# Standalone unit tests (run locally from venv)
# ---------------------------------------------------------------------------

UNIT_TESTS = [
  UnitTestSpec(id="account_security_unit", test_folder="account-security"),
  UnitTestSpec(id="cam_unit", test_folder="cam"),
  UnitTestSpec(id="geometry_unit", test_folder="geometry"),
  UnitTestSpec(id="geospatial_unit", test_folder="geospatial"),
  UnitTestSpec(id="scenescape_unit", test_folder="scenescape"),
  UnitTestSpec(id="schema_unit", test_folder="schema"),
  UnitTestSpec(id="singleton_sensor_unit", test_folder="singleton_sensor"),
  UnitTestSpec(id="timestamp_unit", test_folder="timestamp"),
  UnitTestSpec(id="transform_unit", test_folder="transform"),
  UnitTestSpec(id="views_unit", test_folder="views"),
  UnitTestSpec(id="mesh_util_unit", test_folder="mesh_util"),
  UnitTestSpec(id="robot_vision_unit", test_folder="robot_vision"),
  UnitTestSpec(id="scene_unit", test_folder="scene_pytest"),
  UnitTestSpec(id="uuid_manager_unit", test_folder="uuid_manager"),
  UnitTestSpec(id="vdms_adapter_unit", test_folder="vdms_adapter"),
  UnitTestSpec(id="autocamcalib_unit", test_folder="autocamcalib"),
]


@pytest.fixture(scope="function")
def unit_spec(request):
  """Extract the UnitTestSpec from the parametrize marker."""
  return request.param


@pytest.mark.parametrize(
  "unit_spec",
  UNIT_TESTS,
  ids=[s.id for s in UNIT_TESTS],
  indirect=True,
)
def test_unit(run_unit, unit_spec):
  """Run a standalone unit test locally from the venv."""
  rc = run_unit(unit_spec)
  assert rc == 0, f"Unit test {unit_spec.id} failed with exit code {rc}"


# ---------------------------------------------------------------------------
# Compose-based unit tests (require a compose stack)
# ---------------------------------------------------------------------------

COMPOSE_UNIT_TESTS = [
  FuncTestSpec(
    id="markerless_unit",
    profile=MARKERLESS,
    script="tests/sscape_tests/markerless/",
    require_password=False,
    auth="",
  ),
]


@pytest.fixture(scope="function")
def compose_unit_spec(request):
  """Extract the TestSpec for compose-based unit tests."""
  return request.param


@pytest.mark.parametrize(
  "compose_unit_spec,scenescape_env",
  [(s, s) for s in COMPOSE_UNIT_TESTS],
  ids=[s.id for s in COMPOSE_UNIT_TESTS],
  indirect=True,
)
def test_compose_unit(scenescape_env, run_test, compose_unit_spec):
  """Run a compose-based unit test end-to-end."""
  rc = run_test(compose_unit_spec)
  assert rc == 0, f"Unit test {compose_unit_spec.id} failed with exit code {rc}"
