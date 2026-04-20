#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bridge shared pytest hooks and fixtures from the repository root.

Since tests/pytest.ini exists, pytest treats tests/ as the root directory.
Load the shared root conftest explicitly so options, hooks, and fixtures used
by functional tests are still available when running via tests/.
"""

import importlib.util
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
  sys.path.insert(0, str(_repo_root))

_root_conftest_path = _repo_root / "conftest.py"
_root_conftest_spec = importlib.util.spec_from_file_location(
  "scenescape_root_conftest", _root_conftest_path,
)
_root_conftest = importlib.util.module_from_spec(_root_conftest_spec)
_root_conftest_spec.loader.exec_module(_root_conftest)

for _name in [
  "pytest_addoption",
  "pytest_collection_modifyitems",
  "pytest_runtest_setup",
  "pytest_runtest_call",
  "pytest_runtest_logreport",
  "pytest_configure",
  "initialize_controller_mode",
  "repo_root",
  "version",
  "secrets_dir",
  "supass",
  "params",
  "_docker_prune_at_exit",
  "loopback_hosts",
  "_env_matrix_setup",
  "scenescape_env",
  "full_stack_env",
  "full_stack_video_retail_env",
  "reid_env",
  "reid_semantic_env",
  "full_stack_autocalibration_env",
  "scene_no_db_env",
  "markerless_env",
]:
  if hasattr(_root_conftest, _name):
    globals()[_name] = getattr(_root_conftest, _name)
