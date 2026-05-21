# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from unittest.mock import MagicMock

import tests.common_test_utils as common

TEST_NAME = "NEX-T10700"

# Mock the vdms module before importing controller modules that depend on it.
sys.modules.setdefault('vdms', MagicMock())


def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")
  return


def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return
