#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (C) 2025 Intel Corporation

"""
HLOC patch verification test runner.

Run all verification tests or specific test suites.
"""

import sys
import argparse
import subprocess
from pathlib import Path


def run_test(test_file: Path) -> bool:
    """Run a single test file and return success status."""
    print(f"\nRunning {test_file.name}...")
    result = subprocess.run([sys.executable, str(test_file)], cwd=test_file.parent)
    return result.returncode == 0


def main():
    """Run verification tests."""
    parser = argparse.ArgumentParser(description='Run HLOC verification tests')
    parser.add_argument('--api-only', action='store_true',
                       help='Only run API surface tests')
    parser.add_argument('--functional-only', action='store_true',
                       help='Only run functional tests')
    parser.add_argument('--test', type=str,
                       help='Run specific test (api, extraction, matching, matchers, database, workflows)')
    args = parser.parse_args()
    
    test_dir = Path(__file__).parent
    
    # Define test categories
    api_tests = ['test_api.py']
    functional_tests = [
        'test_extraction.py',
        'test_matching.py',
        'test_matchers.py',
        'test_database.py',
        'test_workflows.py',
    ]
    
    # Select tests to run
    if args.test:
        test_file = f"test_{args.test}.py"
        if not (test_dir / test_file).exists():
            print(f"❌ Test not found: {test_file}")
            print(f"\nAvailable tests:")
            print("  api, extraction, matching, matchers, database, workflows")
            return 1
        tests_to_run = [test_file]
    elif args.api_only:
        tests_to_run = api_tests
    elif args.functional_only:
        tests_to_run = functional_tests
    else:
        tests_to_run = api_tests + functional_tests
    
    print("=" * 80)
    print("HLOC Patch Verification")
    print("=" * 80)
    print(f"\nRunning {len(tests_to_run)} test suite(s)...")
    
    # Run tests
    results = {}
    for test_file in tests_to_run:
        test_path = test_dir / test_file
        if not test_path.exists():
            print(f"\n⚠️  Test not found: {test_file}")
            results[test_file] = False
            continue
        
        results[test_file] = run_test(test_path)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_file, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {status}: {test_file}")
    
    print("\n" + "=" * 80)
    print(f"Total: {passed}/{total} test suites passed")
    print("=" * 80)
    
    if passed == total:
        print("\n✅ All verification tests passed!")
        print("The patched HLOC is functionally equivalent and ready for production.")
        return 0
    else:
        print(f"\n❌ {total - passed} test suite(s) failed")
        print("Please review failures above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
