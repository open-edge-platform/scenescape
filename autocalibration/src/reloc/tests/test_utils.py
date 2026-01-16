# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

"""Test utilities for HLOC verification tests."""

import sys
from pathlib import Path


def setup_hloc_path():
    """Add HLOC to Python path if in HLOC directory."""
    hloc_root = Path.cwd()
    if not (hloc_root / 'hloc' / '__init__.py').exists():
        # Try looking up one directory
        hloc_root = Path.cwd().parent
        if not (hloc_root / 'hloc' / '__init__.py').exists():
            raise RuntimeError(
                f"Must run from HLOC root directory (where hloc/ subdirectory exists)\n"
                f"Current directory: {Path.cwd()}"
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
