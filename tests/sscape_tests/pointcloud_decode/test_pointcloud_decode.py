# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for MQTT point-cloud payload decode / validation (JS).

Runs the Node test harness against pointcloud_decode.mjs (no Docker).

Import path: no sys.path inserts — conftest already adds tests/ and repo root.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

TEST_NAME = "NEX-T28221"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARNESS = Path(__file__).resolve().parent / "run_decode_tests.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_pointcloud_decode_validation():
  """! Positive and negative decode cases for untrusted MQTT payloads. """
  result = subprocess.run(
    ["node", "--test", str(_HARNESS)],
    cwd=str(_REPO_ROOT),
    capture_output=True,
    text=True,
    check=False,
  )
  assert result.returncode == 0, (
    f"node --test failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
  )
