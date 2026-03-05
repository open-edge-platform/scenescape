#!/usr/bin/env python3
"""
Demo script showing how to use the generate_third_party_programs.py with test data
"""

import os
import sys
from pathlib import Path

# Add the script directory to Python path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

from generate_third_party_programs import main


def run_demo():
    """Run demo with test data."""
    test_data_dir = Path(__file__).parent / "test_data"
    
    print("=== Demo: Simple Dependencies ===")
    print("Input: simple_deps.csv")
    print("Running generate_third_party_programs.py...")
    
    # Set up arguments for simple test
    sys.argv = [
        "generate_third_party_programs.py",
        str(test_data_dir / "simple_deps.csv"),
        "--output", str(test_data_dir / "simple_output.txt"),
        "--preamble", str(test_data_dir / "test_preamble.txt"),
        "--licenses-dir", str(test_data_dir / "licenses")
    ]
    
    try:
        main()
        print("✓ Generated: simple_output.txt")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n=== Demo: Complex Dependencies (Multiple Licenses) ===")
    print("Input: complex_deps.csv")
    print("Running generate_third_party_programs.py...")
    
    # Set up arguments for complex test
    sys.argv = [
        "generate_third_party_programs.py", 
        str(test_data_dir / "complex_deps.csv"),
        "--output", str(test_data_dir / "complex_output.txt"),
        "--preamble", str(test_data_dir / "test_preamble.txt"),
        "--licenses-dir", str(test_data_dir / "licenses")
    ]
    
    try:
        main()
        print("✓ Generated: complex_output.txt")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n=== Demo: Special Licenses (Public Domain & Collection) ===")
    print("Input: special_licenses_deps.csv")
    print("Running generate_third_party_programs.py...")
    
    # Set up arguments for special licenses test
    sys.argv = [
        "generate_third_party_programs.py",
        str(test_data_dir / "special_licenses_deps.csv"),
        "--output", str(test_data_dir / "special_licenses_output.txt"),
        "--preamble", str(test_data_dir / "test_preamble.txt"),
        "--licenses-dir", str(test_data_dir / "licenses")
    ]
    
    try:
        main()
        print("✓ Generated: special_licenses_output.txt")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n=== Output Files Created ===")
    for output_file in ["simple_output.txt", "complex_output.txt", "special_licenses_output.txt"]:
        output_path = test_data_dir / output_file
        if output_path.exists():
            print(f"✓ {output_file} ({output_path.stat().st_size} bytes)")
        else:
            print(f"✗ {output_file} (not created)")
    
    print(f"\nOutput files are in: {test_data_dir}")
    print("You can examine them to see the generated third-party programs listings.")
    print("Note: Special licenses (Public Domain, collection of licenses) use explanatory text instead of license files.")


if __name__ == "__main__":
    run_demo()