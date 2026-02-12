#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import sys
from pathlib import Path

# Ensure controller module is importable from controller/src
controller_src = Path(__file__).resolve().parents[1] / 'controller' / 'src'
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

def pytest_addoption(parser):
  """Add shared command-line options for all tests."""
  # Only add if not already defined (to avoid conflicts with test-specific conftest files)
  try:
    parser.addoption(
      "--analytics-only",
      action="store_true",
      default=False,
      help="Enable analytics-only mode for tests (tracker disabled)"
    )
  except ValueError:
    # Option already added by another conftest.py
    pass
