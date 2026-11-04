# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run the Manager PTZ UI module tests in ptz_ui/ with the Node.js test runner.

The modules under test load from manager/src/manager/static; browser-only
dependencies are stubbed by ptz_ui/loader.mjs.

Locally the tests are skipped when Node.js or three.module.js is missing. In CI
(the CI environment variable is set, as in GitHub Actions) they fail instead, so
the coverage cannot be lost silently; the unit test job provides both.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).resolve().parent / "ptz_ui"
REPO_ROOT = Path(__file__).resolve().parents[3]
THREE_JS = REPO_ROOT / "manager" / "src" / "manager" / "static" / "assets" / "three.module.js"
NODE = shutil.which("node")
MIN_NODE_VERSION = (20, 6)  # module.register() for the module loader hooks
TEST_FILES = sorted(TEST_DIR.glob("*.test.mjs"))
REQUIRED = os.environ.get("CI", "").strip().lower() in ("1", "true", "yes")


def _node_version():
  if NODE is None:
    return None
  output = subprocess.run([NODE, "--version"], capture_output=True, text=True, check=False)
  match = re.match(r"v(\d+)\.(\d+)", output.stdout.strip())
  return (int(match.group(1)), int(match.group(2))) if match else None


def _missing_requirement():
  version = _node_version()
  if version is None or version < MIN_NODE_VERSION:
    found = "not found" if version is None else f"{version[0]}.{version[1]}"
    return (f"Node.js >= {MIN_NODE_VERSION[0]}.{MIN_NODE_VERSION[1]} is required "
            f"(found: {found})")
  if not THREE_JS.is_file():
    return (f"{THREE_JS.relative_to(REPO_ROOT)} is missing; download it with "
            "'make -C manager src/manager/static/assets/three.module.js'")
  return None


MISSING_REQUIREMENT = _missing_requirement()


@pytest.fixture(autouse=True)
def _js_runtime():
  if MISSING_REQUIREMENT:
    if REQUIRED:
      pytest.fail(f"Manager PTZ UI tests cannot run in CI: {MISSING_REQUIREMENT}")
    pytest.skip(MISSING_REQUIREMENT)


def test_ptz_ui_test_files_exist():
  assert TEST_FILES, f"no *.test.mjs files in {TEST_DIR}"


@pytest.mark.parametrize("test_file", TEST_FILES, ids=lambda path: path.stem)
def test_ptz_ui_module(test_file):
  result = subprocess.run(
    [NODE, "--import", "./register.mjs", "--test", "--test-reporter=spec", test_file.name],
    cwd=TEST_DIR, capture_output=True, text=True, timeout=120, check=False)
  assert result.returncode == 0, result.stdout + result.stderr
