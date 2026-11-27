# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Load the original MVP from the `*.py.backup` copies next to the package sources.

The backups are the files of commit 5cc7f08a8 that the pre-port cleanup changes (see
implementation.md). `load_legacy()` imports them as a separate package,
`observation_conditioning_legacy`, so the original and the current implementation can run
side by side without touching the working tree::

    legacy = load_legacy()
    legacy.AmodalReasoner(...)          # original behavior
    observation_conditioning.AmodalReasoner(...)   # current implementation
"""

import importlib.util
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

PACKAGE_NAME = "observation_conditioning_legacy"
BACKUP_DIR = Path(__file__).resolve().parents[2] / "python" / "observation_conditioning"
# Import order matters: amodal_reasoner imports the other two.
MODULES = ("constants", "intersection_map", "amodal_reasoner")
BACKUPS = tuple(BACKUP_DIR / f"{name}.py.backup" for name in MODULES)


def load_legacy():
  """Return the legacy package (`AmodalReasoner`, `DepthMap` as attributes); cached."""
  if PACKAGE_NAME in sys.modules and hasattr(sys.modules[PACKAGE_NAME], "AmodalReasoner"):
    return sys.modules[PACKAGE_NAME]
  package = types.ModuleType(PACKAGE_NAME)
  package.__path__ = [str(BACKUP_DIR)]
  sys.modules[PACKAGE_NAME] = package
  for name in MODULES:
    full_name = f"{PACKAGE_NAME}.{name}"
    loader = SourceFileLoader(full_name, str(BACKUP_DIR / f"{name}.py.backup"))
    spec = importlib.util.spec_from_loader(full_name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    loader.exec_module(module)
    setattr(package, name, module)
  package.AmodalReasoner = package.amodal_reasoner.AmodalReasoner
  package.DepthMap = package.intersection_map.DepthMap
  return package
