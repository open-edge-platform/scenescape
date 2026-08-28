# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Add the repo ``radar/`` tooling directory to sys.path for unit tests."""

import sys
from pathlib import Path

_RADAR_DIR = Path(__file__).resolve().parents[3] / "radar"
if str(_RADAR_DIR) not in sys.path:
  sys.path.insert(0, str(_RADAR_DIR))
