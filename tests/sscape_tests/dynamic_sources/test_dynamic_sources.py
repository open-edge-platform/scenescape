# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run source-renderer unit tests using the browser's Three.js dependency."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_dynamic_source_renderer() -> None:
  """Verify geometry, source isolation, validation, and resource lifecycle."""
  harness = Path(__file__).with_name("run_renderer_tests.mjs")
  result = subprocess.run(
    ["node", "--test", str(harness)],
    capture_output=True,
    text=True,
    check=False,
    timeout=30,
  )
  assert result.returncode == 0, (
    f"Source renderer tests failed:\n{result.stdout}\n{result.stderr}"
  )
