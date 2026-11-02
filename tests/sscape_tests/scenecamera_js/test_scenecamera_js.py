# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for SceneCamera calibration-frame request and native-resolution projection (JS).

Runs the Node test harness against scenecamera.js with stubbed browser imports (no Docker).

Import path: no sys.path inserts — conftest already adds tests/ and repo root.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARNESS = Path(__file__).resolve().parent / "run_scenecamera_tests.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_scenecamera_calibration_frame_and_native_resolution():
  """! Calibration frame request flow and native-resolution projection, incl. fallbacks. """
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
