#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration and fixtures for UUID manager tests.
Provides mock objects and test utilities.
"""

import pytest
from unittest.mock import MagicMock, Mock
import tests.common_test_utils as common

TEST_NAME = "NEX-T19884"

@pytest.fixture
def mock_vdms():
  """
  Provides a mocked VDMS database instance.

  Returns:
    MagicMock: Mock VDMS instance with all methods available.
  """
  mock_instance = MagicMock()
  mock_instance.addSchema = Mock(return_value=({'status': 0}, []))
  mock_instance.findSchema = Mock(return_value=({'status': 0}, []))
  mock_instance.addEntry = Mock(return_value=({'status': 0}, []))
  mock_instance.findMatches = Mock(return_value=({'status': 0}, []))
  return mock_instance


def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")

  return


def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return
