#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Manual test runner for pose_from_cluster tests.
This can be run standalone to verify the pose_from_cluster tests work correctly.
"""

import sys
import pytest
from pathlib import Path

def main():
  """Run pose_from_cluster tests."""
  test_file = Path(__file__).parent / "test_localize_scenescape.py"

  print("=" * 80)
  print("Running pose_from_cluster tests...")
  print("=" * 80)

  # Run only the TestPoseFromCluster class
  exit_code = pytest.main([
    str(test_file),
    "-v",
    "-k", "TestPoseFromCluster",
    "--tb=short"
  ])

  if exit_code == 0:
    print("\n" + "=" * 80)
    print("✓ All pose_from_cluster tests passed!")
    print("=" * 80)
  else:
    print("\n" + "=" * 80)
    print("✗ Some tests failed. See output above for details.")
    print("=" * 80)

  return exit_code

if __name__ == "__main__":
  sys.exit(main())
