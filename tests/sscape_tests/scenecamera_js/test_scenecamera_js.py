# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for camera calibration JavaScript.

Runs the Node test harnesses with stubbed browser imports (no Docker).

Import path: no sys.path inserts — conftest already adds tests/ and repo root.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARNESS_DIR = Path(__file__).resolve().parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("harness", ["run_scenecamera_tests.mjs", "scene_registration.test.mjs"])
def test_scenecamera_javascript(harness):
  """Check calibration frame requests and 3D scene registration."""
  result = subprocess.run(
    ["node", "--test", str(_HARNESS_DIR / harness)],
    cwd=str(_REPO_ROOT),
    capture_output=True,
    text=True,
    check=False,
  )
  assert result.returncode == 0, (
    f"node --test failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
  )
