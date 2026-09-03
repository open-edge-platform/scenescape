# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Early Django bootstrap for host unit tests (loaded via pytest_plugins)."""

import importlib.util
import os
import sys
import types
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent

if str(_TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(_TESTS_DIR))

_manager_django_src = _REPO_ROOT / "manager" / "src" / "manager"
if "manager" not in sys.modules and _manager_django_src.is_dir():
  spec = importlib.util.spec_from_file_location(
    "manager",
    _manager_django_src / "__init__.py",
    submodule_search_locations=[str(_manager_django_src)],
  )
  manager_mod = importlib.util.module_from_spec(spec)
  sys.modules["manager"] = manager_mod
  spec.loader.exec_module(manager_mod)

  _secrets_file = _REPO_ROOT / "manager" / "secrets" / "django" / "secrets.py"
  if _secrets_file.is_file() and "manager.secrets" not in sys.modules:
    sec_spec = importlib.util.spec_from_file_location(
      "manager.secrets", _secrets_file,
    )
    sec_mod = importlib.util.module_from_spec(sec_spec)
    sys.modules["manager.secrets"] = sec_mod
    sec_spec.loader.exec_module(sec_mod)

  _templatetags_dir = _REPO_ROOT / "manager" / "src" / "templatetags"
  if _templatetags_dir.is_dir() and "manager.templatetags" not in sys.modules:
    tt_mod = types.ModuleType("manager.templatetags")
    tt_mod.__path__ = [str(_templatetags_dir)]
    tt_mod.__package__ = "manager.templatetags"
    sys.modules["manager.templatetags"] = tt_mod

os.environ.setdefault(
  "DJANGO_SETTINGS_MODULE",
  "sscape_tests.settings_unittest",
)
