#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
unit test wrappers.

Each entry maps to an existing Makefile target in tests/Makefile.sscape.
Unit tests using `unit-recipe` run in a standalone container (no compose).
Unit tests using `unit-docker-compose-recipe` require a compose stack.
"""

import pytest

from conftest import FuncTestSpec, UnitTestSpec
from utils.profiles import MARKERLESS


# ---------------------------------------------------------------------------
# Standalone unit tests (unit-recipe: no compose, just docker run)
# ---------------------------------------------------------------------------

UNIT_TESTS = [
  # manager-test image
  UnitTestSpec(id="account_security_unit", test_folder="account-security", docker_image="manager-test"),
  UnitTestSpec(id="cam_unit", test_folder="cam", docker_image="manager-test"),
  UnitTestSpec(id="geometry_unit", test_folder="geometry", docker_image="manager-test"),
  UnitTestSpec(id="geospatial_unit", test_folder="geospatial", docker_image="manager-test"),
  UnitTestSpec(id="scenescape_unit", test_folder="scenescape", docker_image="manager-test"),
  UnitTestSpec(id="schema_unit", test_folder="schema", docker_image="manager-test"),
  UnitTestSpec(id="singleton_sensor_unit", test_folder="singleton_sensor", docker_image="manager-test"),
  UnitTestSpec(id="timestamp_unit", test_folder="timestamp", docker_image="manager-test"),
  UnitTestSpec(id="transform_unit", test_folder="transform", docker_image="manager-test"),
  UnitTestSpec(id="views_unit", test_folder="views", docker_image="manager-test"),

  # controller-test image
  UnitTestSpec(id="mesh_util_unit", test_folder="mesh_util", docker_image="controller-test"),
  UnitTestSpec(id="robot_vision_unit", test_folder="robot_vision", docker_image="controller-test"),
  UnitTestSpec(id="scene_unit", test_folder="scene_pytest", docker_image="controller-test"),
  UnitTestSpec(id="uuid_manager_unit", test_folder="uuid_manager", docker_image="controller-test"),
  UnitTestSpec(id="vdms_adapter_unit", test_folder="vdms_adapter", docker_image="controller-test"),

  # autocalibration-test image
  UnitTestSpec(id="autocamcalib_unit", test_folder="autocamcalib", docker_image="autocalibration-test"),
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
  """Run a standalone unit test inside a Docker container."""
  rc = run_unit(unit_spec)
  assert rc == 0, f"Unit test {unit_spec.id} failed with exit code {rc}"


# ---------------------------------------------------------------------------
# Compose-based unit tests (unit-docker-compose-recipe)
# ---------------------------------------------------------------------------

COMPOSE_UNIT_TESTS = [
  FuncTestSpec(
    id="markerless_unit",
    profile=MARKERLESS,
    script="tests/sscape_tests/markerless/",
    test_image="autocalibration-test",
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
