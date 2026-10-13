# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Import helpers for scenescape-setup skill scripts (not a Python package)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_SCRIPTS = _REPO_ROOT / ".github" / "skills" / "scenescape-setup" / "scripts"

# Skill scripts import siblings (e.g. deploy_inputs) as top-level modules.
if str(_SKILL_SCRIPTS) not in sys.path:
  sys.path.insert(0, str(_SKILL_SCRIPTS))


def _load_skill_module(module_name: str, filename: str):
  path = _SKILL_SCRIPTS / filename
  spec = importlib.util.spec_from_file_location(module_name, path)
  if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load skill script {path}")
  module = importlib.util.module_from_spec(spec)
  sys.modules[module_name] = module
  spec.loader.exec_module(module)
  return module


@pytest.fixture(scope="module")
def bootstrap_deploy():
  return _load_skill_module("scenescape_setup_bootstrap_deploy", "bootstrap_deploy.py")


@pytest.fixture(scope="module")
def download_model():
  return _load_skill_module("scenescape_setup_download_model", "download_model.py")
