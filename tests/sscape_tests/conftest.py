#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared conftest for sscape_tests unit tests."""

import sys
from pathlib import Path

_NATIVE_ONLY_DIRS = {"autocamcalib", "markerless", "robot_vision"}

_controller_src = Path(__file__).resolve().parent.parent.parent / "controller" / "src"
if str(_controller_src) not in sys.path:
  sys.path.insert(0, str(_controller_src))

def pytest_ignore_collect(collection_path, config):
  """Skip test directories that need C++ extensions not installed on host."""
  if collection_path.is_dir() and collection_path.name in _NATIVE_ONLY_DIRS:
    return True
