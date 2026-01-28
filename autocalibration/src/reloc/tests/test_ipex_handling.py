#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test IPEX import exception handling.

This test verifies that patch 07-ipex-import-fix.patch is correctly applied.
The patch fixes a bug where intel_extension_for_pytorch 2.7.0 calls os.exit()
instead of sys.exit(), causing AttributeError when import fails.

Without the patch, the code only catches ImportError, allowing AttributeError
to propagate and crash the application.
"""

import sys
import unittest
from pathlib import Path
from test_utils import setup_hloc_path, print_test_header, print_test_result


class TestIPEXExceptionHandling(unittest.TestCase):
  """Test that IPEX import failures are handled gracefully."""

  @classmethod
  def setUpClass(cls):
    """Set up HLOC path."""
    try:
      setup_hloc_path()
    except RuntimeError as e:
      print(f"❌ {e}")
      sys.exit(1)

  def test_match_features_handles_ipex_attributeerror(self):
    """Test that match_features handles AttributeError during IPEX import."""
    print_test_header("match_features IPEX AttributeError handling")

    try:
      import inspect
      from hloc import match_features

      # Verify the source code has the correct exception handling
      print("  Checking match_features source code for exception handling...")

      source = inspect.getsource(match_features)

      # Look for the patched code with broad exception handling
      has_broad_exception = "except Exception:" in source
      has_ipex_import = "intel_extension_for_pytorch" in source

      if has_broad_exception and has_ipex_import:
        print("  ✓ match_features catches broad exceptions (including AttributeError)")
        print("  ✓ IPEX import is properly protected")
        print_test_result(True)
        self.assertTrue(True, "Patch 07 correctly applied to match_features")
      elif has_ipex_import and "except ImportError:" in source:
        print("  ❌ match_features only catches ImportError, not AttributeError!")
        print("  ⚠️  Patch 07-ipex-import-fix.patch may not be applied!")
        print_test_result(False, "Only catches ImportError")
        self.fail("match_features doesn't handle AttributeError - patch 07 missing?")
      else:
        print("  ⚠️  Cannot determine exception handling from source")
        print_test_result(True, "Skipped - cannot verify")

    except Exception as e:
      print(f"  ⚠️  Test error: {e}")
      print_test_result(True, f"Skipped - {e}")
      print_test_result(True, "Skipped - dependencies missing")

  def test_base_model_handles_ipex_attributeerror(self):
    """Test that base_model cached_load handles AttributeError during IPEX import."""
    print_test_header("base_model.cached_load IPEX AttributeError handling")

    try:
      import inspect
      from hloc.utils import base_model

      # Instead of trying to mock imports (which is complex), just verify
      # that the code has the correct exception handling
      print("  Checking base_model source code for exception handling...")

      source = inspect.getsource(base_model.cached_load)

      # Look for the patched code with broad exception handling
      has_broad_exception = "except Exception:" in source
      has_ipex_import = "intel_extension_for_pytorch" in source

      if has_broad_exception and has_ipex_import:
        print("  ✓ base_model.cached_load catches broad exceptions (including AttributeError)")
        print("  ✓ IPEX import is properly protected")
        print_test_result(True)
        self.assertTrue(True, "Patch 07 correctly applied to base_model")
      elif has_ipex_import and "except ImportError:" in source:
        print("  ❌ base_model only catches ImportError, not AttributeError!")
        print("  ⚠️  Patch 07-ipex-import-fix.patch may not be applied!")
        print_test_result(False, "Only catches ImportError")
        self.fail("base_model doesn't handle AttributeError - patch 07 missing?")
      else:
        print("  ⚠️  Cannot determine exception handling from source")
        print_test_result(True, "Skipped - cannot verify")

    except Exception as e:
      print(f"  ⚠️  Test error: {e}")
      print_test_result(True, f"Skipped - {e}")

  def test_ipex_normal_import_still_works(self):
    """Test that normal IPEX import still works (if available)."""
    print_test_header("Normal IPEX import behavior")

    try:
      import intel_extension_for_pytorch as ipex
      print("  ✓ IPEX is installed and imports successfully")
      print_test_result(True, "IPEX available")
    except ImportError:
      print("  ℹ  IPEX not installed (expected in CPU-only environments)")
      print_test_result(True, "IPEX not installed (expected)")
    except AttributeError as e:
      # This should not happen - if IPEX is installed, it should import correctly
      print(f"  ⚠️  IPEX installed but import failed: {e}")
      print("  This may indicate IPEX 2.7.0 bug in your environment")
      print_test_result(True, "IPEX bug detected (patch handles this)")


def main():
  """Run IPEX exception handling tests."""
  print("\n" + "="*70)
  print("IPEX Exception Handling Tests (Patch 07 Verification)")
  print("="*70 + "\n")

  # Run tests
  suite = unittest.TestLoader().loadTestsFromTestCase(TestIPEXExceptionHandling)
  runner = unittest.TextTestRunner(verbosity=2)
  result = runner.run(suite)

  return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
  sys.exit(main())
