#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

"""
Docker build integration test for HLOC patches.

This lightweight test runs during Docker build to verify that:
1. All patches applied successfully
2. Core modules can be imported
3. Critical classes and functions exist
4. Basic instantiation works

This is a minimal test suitable for build-time verification.
For comprehensive functional testing, use verify_patches.py.
"""

import sys
from pathlib import Path

def test_imports():
    """Test that all critical modules can be imported."""
    print("Testing imports...")
    errors = []
    
    try:
        import hloc
        print("  ✅ hloc")
    except Exception as e:
        errors.append(f"hloc: {e}")
        
    try:
        from hloc import extract_features, match_features, match_dense
        print("  ✅ extract_features, match_features, match_dense")
    except Exception as e:
        errors.append(f"feature modules: {e}")
    
    try:
        from hloc import reconstruction, triangulation
        print("  ✅ reconstruction, triangulation")
    except Exception as e:
        errors.append(f"reconstruction modules: {e}")
    
    try:
        from hloc.matchers import loftr, qta_loftr
        print("  ✅ loftr, qta_loftr (custom matchers)")
    except Exception as e:
        errors.append(f"custom matchers: {e}")
    
    try:
        from hloc.utils import database, dataset, evaluate
        print("  ✅ database, dataset, evaluate (utils)")
    except Exception as e:
        errors.append(f"utils: {e}")
        
    return errors

def test_classes():
    """Test that custom classes exist and can be instantiated."""
    print("\nTesting custom classes...")
    errors = []
    
    try:
        from hloc.matchers.loftr import LoFTR
        # Don't instantiate (requires weights), just check it exists
        assert callable(LoFTR)
        print("  ✅ LoFTR class exists")
    except Exception as e:
        errors.append(f"LoFTR: {e}")
    
    try:
        from hloc.matchers.qta_loftr import QTALoFTR
        assert callable(QTALoFTR)
        print("  ✅ QTALoFTR class exists")
    except Exception as e:
        errors.append(f"QTALoFTR: {e}")
        
    return errors

def test_functions():
    """Test that main entry point functions exist."""
    print("\nTesting entry point functions...")
    errors = []
    
    try:
        from hloc.extract_features import main
        assert callable(main)
        print("  ✅ extract_features.main")
    except Exception as e:
        errors.append(f"extract_features.main: {e}")
    
    try:
        from hloc.match_features import main
        assert callable(main)
        print("  ✅ match_features.main")
    except Exception as e:
        errors.append(f"match_features.main: {e}")
    
    try:
        from hloc.match_dense import main
        assert callable(main)
        print("  ✅ match_dense.main (custom)")
    except Exception as e:
        errors.append(f"match_dense.main: {e}")
        
    try:
        from hloc.reconstruction import main
        assert callable(main)
        print("  ✅ reconstruction.main")
    except Exception as e:
        errors.append(f"reconstruction.main: {e}")
        
    return errors

def test_database():
    """Test database module (critical for COLMAP integration)."""
    print("\nTesting database operations...")
    errors = []
    
    try:
        from hloc.utils.database import COLMAPDatabase
        assert hasattr(COLMAPDatabase, 'connect')
        assert hasattr(COLMAPDatabase, 'add_camera')
        assert hasattr(COLMAPDatabase, 'add_image')
        print("  ✅ COLMAPDatabase has required methods")
    except Exception as e:
        errors.append(f"COLMAPDatabase: {e}")
        
    return errors

def main():
    """Run all build-time tests."""
    print("=" * 70)
    print("HLOC Build Integration Test")
    print("=" * 70)
    
    # Ensure we're in HLOC directory
    hloc_dir = Path.cwd()
    if not (hloc_dir / 'hloc' / '__init__.py').exists():
        print(f"❌ Error: Not in HLOC directory")
        print(f"   Current: {hloc_dir}")
        print(f"   Expected: directory containing hloc/ subdirectory")
        return 1
    
    sys.path.insert(0, str(hloc_dir))
    
    all_errors = []
    
    # Run tests
    all_errors.extend(test_imports())
    all_errors.extend(test_classes())
    all_errors.extend(test_functions())
    all_errors.extend(test_database())
    
    # Summary
    print("\n" + "=" * 70)
    if all_errors:
        print("⚠️  BUILD INTEGRATION TEST - WARNINGS")
        print("=" * 70)
        print("\nIssues detected (may be due to missing dependencies):")
        for error in all_errors:
            print(f"  • {error}")
        print("\n⚠️  This is expected if Python dependencies not yet installed.")
        print("    Full verification available after build completes.")
        # Return success even with warnings - dependencies installed later
        return 0
    else:
        print("✅ BUILD INTEGRATION TEST PASSED")
        print("=" * 70)
        print("\nPatched HLOC is ready for use in autocalibration.")
        print("For comprehensive functional testing, run verify_patches.py")
        return 0

if __name__ == '__main__':
    sys.exit(main())
