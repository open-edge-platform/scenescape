# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test utilities for HLOC verification tests."""

import sys
from pathlib import Path


def setup_hloc_path():
  """Add HLOC to Python path if in HLOC directory, or verify it's installed."""
  # First check if hloc is already importable (installed via pip)
  try:
    import hloc
    if hloc.__file__:
      return Path(hloc.__file__).parent.parent
    # If __file__ is None (namespace package or mounted volume), hloc is still importable
    return Path.cwd()
  except ImportError:
    pass

  # Fall back to looking for hloc directory (development mode)
  hloc_root = Path.cwd()
  if not (hloc_root / 'hloc' / '__init__.py').exists():
    # Try looking up one directory
    hloc_root = Path.cwd().parent
    if not (hloc_root / 'hloc' / '__init__.py').exists():
      raise RuntimeError(
        f"HLOC not installed and not found in current directory\n"
        f"Current directory: {Path.cwd()}\n"
        f"Please install hloc or run from HLOC root directory"
      )
  sys.path.insert(0, str(hloc_root))
  return hloc_root


def print_test_header(test_name: str):
  """Print formatted test header."""
  print(f"\n{'=' * 80}")
  print(f"TEST: {test_name}")
  print('=' * 80)


def print_test_result(passed: bool, message: str = ""):
  """Print formatted test result."""
  if passed:
    print(f"\n✅ PASSED{': ' + message if message else ''}")
  else:
    print(f"\n❌ FAILED{': ' + message if message else ''}")
