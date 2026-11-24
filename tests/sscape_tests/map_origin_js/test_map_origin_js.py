# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Behavior tests for the 2D map origin pixel/meter conversions in utils.js."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_map_origin_js():
  harness = Path(__file__).with_name("run_map_origin_tests.mjs")
  result = subprocess.run(
    ["node", "--experimental-vm-modules", "--test", str(harness)],
    cwd=Path(__file__).resolve().parents[3],
    capture_output=True,
    text=True,
    check=False,
  )
  assert result.returncode == 0, (
    f"Map origin JS tests failed\n{result.stdout}\n{result.stderr}"
  )
