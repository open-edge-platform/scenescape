#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import pytest

from scene_common.scenescape import SceneLoader
import tests.common_test_utils as common

sscape_tests_path = os.path.dirname(os.path.realpath(__file__))
CONFIG_FULLPATH = os.path.join(sscape_tests_path, "config.json")

TEST_NAME = "NEX-T10450"
def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")

  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

@pytest.fixture(scope="module")
def manager():
  """! Creates a scenescape class object as a fixture. """

  return SceneLoader(CONFIG_FULLPATH)
