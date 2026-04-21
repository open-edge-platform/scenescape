#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Test module imports and API surface."""

import sys
from pathlib import Path
from test_utils import setup_hloc_path, print_test_header, print_test_result


def test_core_imports():
  """Test core HLOC module imports."""
  print_test_header("Core Module Imports")

  modules = [
    'hloc',
    'hloc.extract_features',
    'hloc.match_features',
    'hloc.match_dense',
    'hloc.reconstruction',
    'hloc.triangulation',
    'hloc.localize_sfm',
    'hloc.pairs_from_retrieval',
    'hloc.pairs_from_covisibility',
  ]

  failed = []
  for module in modules:
    try:
      __import__(module)
      print(f"  ✅ {module}")
    except ImportError as e:
      print(f"  ❌ {module}: {e}")
      failed.append(module)

  passed = len(failed) == 0
  print_test_result(passed, f"Imported {len(modules) - len(failed)}/{len(modules)} modules")
  return passed


def test_custom_modules():
  """Test SceneScape custom module imports."""
  print_test_header("Custom Module Imports")

  modules = {
    'Custom Matchers': ['hloc.matchers.loftr'],
    'Custom Utils': ['hloc.utils.dataset', 'hloc.utils.evaluate'],
    'Pipeline Utils': ['hloc.pipelines.utils'],
  }

  all_passed = True
  for category, module_list in modules.items():
    print(f"\n  {category}:")
    for module in module_list:
      try:
        __import__(module)
        print(f"  ✅ {module}")
      except ImportError as e:
        print(f"  ❌ {module}: {e}")
        all_passed = False

  print_test_result(all_passed)
  return all_passed


def test_function_signatures():
  """Test critical function signatures."""
  print_test_header("Function Signatures")

  import inspect

  functions = [
    ('hloc.extract_features', 'main'),
    ('hloc.match_features', 'main'),
    ('hloc.match_dense', 'main'),
    ('hloc.reconstruction', 'main'),
    ('hloc.triangulation', 'main'),
  ]

  all_passed = True
  for module_name, func_name in functions:
    try:
      module = __import__(module_name, fromlist=[func_name])
      if not hasattr(module, func_name):
        print(f"  ❌ {module_name}.{func_name} not found")
        all_passed = False
      else:
        func = getattr(module, func_name)
        sig = inspect.signature(func)
        print(f"  ✅ {module_name}.{func_name}{sig}")
    except Exception as e:
      print(f"  ❌ {module_name}.{func_name}: {e}")
      all_passed = False

  print_test_result(all_passed)
  return all_passed


def test_matcher_classes():
  """Test custom matcher classes exist."""
  print_test_header("Matcher Classes")

  classes = [
    ('hloc.matchers.loftr', 'LoFTR'),
    # QTA-LoFTR not used in SceneScape
  ]

  all_passed = True
  for module_name, class_name in classes:
    try:
      module = __import__(module_name, fromlist=[class_name])
      if not hasattr(module, class_name):
        print(f"  ❌ {module_name}.{class_name} not found")
        all_passed = False
      else:
        print(f"  ✅ {module_name}.{class_name}")
    except Exception as e:
      print(f"  ❌ {module_name}.{class_name}: {e}")
      all_passed = False

  print_test_result(all_passed)
  return all_passed


def main():
  """Run API surface tests."""
  try:
    setup_hloc_path()
  except RuntimeError as e:
    print(f"❌ {e}")
    return 1

  tests = [
    test_core_imports,
    test_custom_modules,
    test_function_signatures,
    test_matcher_classes,
  ]

  results = []
  for test in tests:
    try:
      results.append(test())
    except Exception as e:
      print(f"\n❌ Test crashed: {e}")
      import traceback
      traceback.print_exc()
      results.append(False)

  print("\n" + "=" * 80)
  print(f"API Tests: {sum(results)}/{len(results)} passed")
  print("=" * 80)

  return 0 if all(results) else 1


if __name__ == '__main__':
  sys.exit(main())
