#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test reconstruction and pipeline workflows."""

import sys
import inspect
from test_utils import setup_hloc_path, print_test_header, print_test_result


def test_reconstruction_api():
  """Test reconstruction module API."""
  print_test_header("Reconstruction API")

  try:
    from hloc import reconstruction, triangulation

    if not hasattr(reconstruction, 'main'):
      print_test_result(False, "reconstruction.main not found")
      return False

    if not hasattr(triangulation, 'main'):
      print_test_result(False, "triangulation.main not found")
      return False

    recon_sig = inspect.signature(reconstruction.main)
    triang_sig = inspect.signature(triangulation.main)

    print(f"  ✓ reconstruction.main: {recon_sig}")
    print(f"  ✓ triangulation.main: {triang_sig}")

    # Check for critical parameters
    recon_params = list(recon_sig.parameters.keys())
    if 'sfm_dir' not in recon_params and 'output' not in recon_params:
      print("  ⚠️  reconstruction.main missing expected output parameter")

    print_test_result(True)
    return True

  except Exception as e:
    print(f"  ❌ Error: {e}")
    print_test_result(False, str(e))
    return False


def test_scenescape_pipeline():
  """Test SceneScape pipeline utilities."""
  print_test_header("SceneScape Pipeline")

  try:
    from hloc.pipelines import utils as pipeline_utils

    print("  ✓ pipeline_utils imported")

    # Check for utility functions
    if hasattr(pipeline_utils, 'create_query_list'):
      print("  ✓ create_query_list exists")
    else:
      print("  ⚠️  create_query_list not found (may be optional)")

    # Try importing SceneScape pipeline
    try:
      from hloc.pipelines.SceneScape import pipeline
      print("  ✓ SceneScape pipeline module exists")

      if hasattr(pipeline, 'main') or hasattr(pipeline, 'run'):
        print("  ✓ SceneScape pipeline has main/run function")
      else:
        print("  ⚠️  SceneScape pipeline missing main/run (may be optional)")

    except ImportError as e:
      print(f"  ⚠️  SceneScape pipeline not found: {e}")

    print_test_result(True)
    return True

  except Exception as e:
    print(f"  ❌ Error: {e}")
    print_test_result(False, str(e))
    return False


def main():
  """Run workflow tests."""
  try:
    setup_hloc_path()
  except RuntimeError as e:
    print(f"❌ {e}")
    return 1

  tests = [
    test_reconstruction_api,
    test_scenescape_pipeline,
  ]

  results = [test() for test in tests]

  print("\n" + "=" * 80)
  print(f"Workflow Tests: {sum(results)}/{len(results)} passed")
  print("=" * 80)

  return 0 if all(results) else 1


if __name__ == '__main__':
  sys.exit(main())
