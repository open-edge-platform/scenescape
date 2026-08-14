#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared conftest for sscape_tests unit tests.

Sets up Django with the SQLite-based settings_unittest module before
any tests are collected.  Creates a ``manager`` package alias pointing
at ``manager/src/django/`` so that ``from manager.settings import *``
works on the host (inside Docker this mapping is done by the Dockerfile
COPY step).
"""

import importlib
import os
import sys
from pathlib import Path

# Directories that require C++ extensions not available on the host.
# Listed as paths relative to this conftest's directory.
_NATIVE_ONLY_DIRS = {"autocamcalib", "markerless", "robot_vision"}

# Import controller module
_controller_src = Path(__file__).resolve().parent.parent.parent / "controller" / "src"
if str(_controller_src) not in sys.path:
  sys.path.insert(0, str(_controller_src))

def pytest_ignore_collect(collection_path, config):
  """Skip test directories that need C++ extensions not installed on host."""
  if collection_path.is_dir() and collection_path.name in _NATIVE_ONLY_DIRS:
    return True

# Ensure repo root is on sys.path so "tests.sscape_tests.settings_unittest"
# and other top-level imports resolve.
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
  sys.path.insert(0, str(_repo_root))

# The Django app source lives at manager/src/django/ but is imported as
# ``manager`` (the Dockerfile copies it to $SCENESCAPE_HOME/manager/).
# On the host we create a sys.modules alias so ``from manager.settings``
# works without a container.
_manager_django_src = _repo_root / "manager" / "src" / "manager"
if "manager" not in sys.modules and _manager_django_src.is_dir():
  spec = importlib.util.spec_from_file_location(
    "manager",
    _manager_django_src / "__init__.py",
    submodule_search_locations=[str(_manager_django_src)],
  )
  manager_mod = importlib.util.module_from_spec(spec)
  sys.modules["manager"] = manager_mod
  spec.loader.exec_module(manager_mod)

  # The Django settings does ``from manager.secrets import *``.  Inside
  # the container secrets.py lives alongside the app code; on the host
  # it is a generated file at manager/secrets/django/secrets.py.
  _secrets_file = _repo_root / "manager" / "secrets" / "django" / "secrets.py"
  if _secrets_file.is_file() and "manager.secrets" not in sys.modules:
    sec_spec = importlib.util.spec_from_file_location(
      "manager.secrets", _secrets_file,
    )
    sec_mod = importlib.util.module_from_spec(sec_spec)
    sys.modules["manager.secrets"] = sec_mod
    sec_spec.loader.exec_module(sec_mod)

  # templatetags live at manager/src/templatetags/ on the host but Django
  # expects them at manager/templatetags/ (as a sub-package of the app).
  _templatetags_dir = _repo_root / "manager" / "src" / "templatetags"
  if _templatetags_dir.is_dir() and "manager.templatetags" not in sys.modules:
    import types
    tt_mod = types.ModuleType("manager.templatetags")
    tt_mod.__path__ = [str(_templatetags_dir)]
    tt_mod.__package__ = "manager.templatetags"
    sys.modules["manager.templatetags"] = tt_mod

os.environ.setdefault(
  "DJANGO_SETTINGS_MODULE",
  "tests.sscape_tests.settings_unittest",
)

try:
  import django
  django.setup()
except Exception:
  # Django setup may fail if optional deps are missing; let pytest
  # report the error per-test rather than blocking all collection.
  pass
