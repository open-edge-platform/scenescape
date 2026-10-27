# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Behavior tests for the Manager's read-only map-source previews."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_map_source_preview():
  harness = Path(__file__).with_name("run_preview_tests.mjs")
  result = subprocess.run(
    ["node", "--experimental-vm-modules", "--test", str(harness)],
    cwd=Path(__file__).resolve().parents[3],
    capture_output=True,
    text=True,
    check=False,
  )
  assert result.returncode == 0, (
    f"Map-source preview tests failed\n{result.stdout}\n{result.stderr}"
  )