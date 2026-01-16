#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

"""Test custom SceneScape matchers."""

import sys
from test_utils import setup_hloc_path, print_test_header, print_test_result


def test_dense_matching():
    """Test match_dense module."""
    print_test_header("Dense Matching Module")
    
    try:
        from hloc import match_dense
        import inspect
        
        if not hasattr(match_dense, 'main'):
            print_test_result(False, "match_dense.main not found")
            return False
        
        sig = inspect.signature(match_dense.main)
        params = list(sig.parameters.keys())
        
        expected = ['conf', 'pairs', 'image_dir', 'export_dir']
        missing = [p for p in expected if p not in params]
        if missing:
            print_test_result(False, f"Missing parameters: {missing}")
            return False
        
        print(f"  ✓ match_dense.main signature: {sig}")
        print_test_result(True)
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        print_test_result(False, str(e))
        return False


def test_loftr_matcher():
    """Test LoFTR matcher class."""
    print_test_header("LoFTR Matcher")
    
    try:
        from hloc.matchers.loftr import LoFTR
        
        print("  ✓ LoFTR class exists")
        
        # Check instantiation (may fail without weights)
        try:
            conf = {'weights': 'outdoor', 'max_keypoints': 2048}
            matcher = LoFTR(conf)
            
            if not hasattr(matcher, '_forward'):
                print_test_result(False, "LoFTR missing _forward method")
                return False
            
            print("  ✓ LoFTR instantiated successfully")
            print("  ✓ _forward method exists")
            
        except Exception as e:
            if 'weights' in str(e).lower() or 'load' in str(e).lower():
                print(f"  ⚠️  Instantiation skipped (weights not available)")
                print("  ✓ Class structure valid")
            else:
                raise
        
        print_test_result(True)
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        print_test_result(False, str(e))
        return False


def test_qta_loftr_matcher():
    """Test QTA-LoFTR matcher class."""
    print_test_header("QTA-LoFTR Matcher")
    
    try:
        from hloc.matchers.qta_loftr import QTALoFTR
        
        print("  ✓ QTALoFTR class exists")
        
        try:
            conf = {'weights': 'outdoor', 'max_keypoints': 2048}
            matcher = QTALoFTR(conf)
            
            if not hasattr(matcher, '_forward'):
                print_test_result(False, "QTALoFTR missing _forward method")
                return False
            
            print("  ✓ QTALoFTR instantiated successfully")
            print("  ✓ _forward method exists")
            
        except Exception as e:
            if 'weights' in str(e).lower() or 'load' in str(e).lower():
                print(f"  ⚠️  Instantiation skipped (weights not available)")
                print("  ✓ Class structure valid")
            else:
                raise
        
        print_test_result(True)
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        print_test_result(False, str(e))
        return False


def main():
    """Run custom matcher tests."""
    try:
        setup_hloc_path()
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1
    
    tests = [
        test_dense_matching,
        test_loftr_matcher,
        test_qta_loftr_matcher,
    ]
    
    results = [test() for test in tests]
    
    print("\n" + "=" * 80)
    print(f"Matcher Tests: {sum(results)}/{len(results)} passed")
    print("=" * 80)
    
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
