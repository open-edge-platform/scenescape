# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest setup for the tracker evaluation tests."""

import sys
from pathlib import Path

# Tests import the evaluation packages (utils, visualization, evaluators, ...) from this directory.
_EVALUATION_ROOT = str(Path(__file__).parent)
if _EVALUATION_ROOT not in sys.path:
  sys.path.insert(0, _EVALUATION_ROOT)
