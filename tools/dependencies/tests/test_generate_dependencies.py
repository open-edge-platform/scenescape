#!/usr/bin/env python3
"""
Test script for generate_dependencies.py
"""

import os
import tempfile
import csv
import shutil
from pathlib import Path
import sys

# Add the script directory to Python path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

from generate_dependencies import process_dependency_files, parse_apt_dependency, parse_pip_dependency


def test_parsing_functions():
    """Test the individual parsing functions."""
    print("Testing parsing functions...")

    # Test APT dependency parsing
    apt_line = "libxkbcommon-x11-0:amd64 1.6.0-1build1 amd64"
    expected_apt = "libxkbcommon-x11-0:amd64:1.6.0-1build1"
    result_apt = parse_apt_dependency(apt_line)
    assert result_apt == expected_apt, f"APT parsing failed: got {result_apt}, expected {expected_apt}"
    print(f"✓ APT parsing: {apt_line} -> {result_apt}")

    # Test pip dependency parsing
    pip_line = "ConfigArgParse==1.7.1"
    expected_pip = "ConfigArgParse==1.7.1"
    result_pip = parse_pip_dependency(pip_line)
    assert result_pip == expected_pip, f"Pip parsing failed: got {result_pip}, expected {expected_pip}"
    print(f"✓ Pip parsing: {pip_line} -> {result_pip}")

    print("All parsing tests passed!")


def test_full_processing():
    """Test the full processing with sample data."""
    print("\nTesting full processing...")

    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test APT dependency file
        apt_file = temp_path / "scenescape-controller-apt-deps.txt"
        with open(apt_file, 'w') as f:
            f.write("libxkbcommon-x11-0:amd64 1.6.0-1build1 amd64\n")
            f.write("fontconfig 2.15.0-1.1ubuntu2 amd64\n")
            f.write("ca-certificates 20240203 all\n")

        # Create test pip dependency file
        pip_file = temp_path / "scenescape-controller-pip-deps.txt"
        with open(pip_file, 'w') as f:
            f.write("ConfigArgParse==1.7.1\n")
            f.write("requests==2.32.3\n")

        # Create another image's files
        apt_file2 = temp_path / "scenescape-manager-apt-deps.txt"
        with open(apt_file2, 'w') as f:
            f.write("apache2 2.4.52-1ubuntu4.15 amd64\n")

        pip_file2 = temp_path / "scenescape-manager-pip-deps.txt"
        with open(pip_file2, 'w') as f:
            f.write("Flask==3.1.1\n")

        # Process the files
        dependencies = process_dependency_files(str(temp_path))

        # Verify results
        expected_dependencies = [
            ("scenescape-controller", "libxkbcommon-x11-0:amd64:1.6.0-1build1", "Ubuntu"),
            ("scenescape-controller", "fontconfig:2.15.0-1.1ubuntu2", "Ubuntu"),
            ("scenescape-controller", "ca-certificates:20240203", "Ubuntu"),
            ("scenescape-controller", "ConfigArgParse==1.7.1", "pypi"),
            ("scenescape-controller", "requests==2.32.3", "pypi"),
            ("scenescape-manager", "apache2:2.4.52-1ubuntu4.15", "Ubuntu"),
            ("scenescape-manager", "Flask==3.1.1", "pypi"),
        ]

        # Sort both lists for comparison
        dependencies.sort()
        expected_dependencies.sort()

        print(f"Found {len(dependencies)} dependencies:")
        for dep in dependencies:
            print(f"  {dep}")

        # Check if we got the expected number of dependencies
        assert len(dependencies) == len(expected_dependencies), \
            f"Expected {len(expected_dependencies)} dependencies, got {len(dependencies)}"

        # Check each dependency
        for i, (expected, actual) in enumerate(zip(expected_dependencies, dependencies)):
            assert actual == expected, \
                f"Dependency {i} mismatch: expected {expected}, got {actual}"

        print("✓ Full processing test passed!")


def test_with_real_data():
    """Test with a small subset of real data."""
    print("\nTesting with real data...")

    # Test with the actual build folder
    build_folder = "/home/labrat/tdorau/repos/scenescape/build"

    if os.path.exists(build_folder):
        dependencies = process_dependency_files(build_folder)
        print(f"✓ Processed {len(dependencies)} dependencies from real data")

        # Show a few examples
        print("Sample dependencies:")
        for i, dep in enumerate(dependencies[:5]):
            print(f"  {dep}")
        if len(dependencies) > 5:
            print("  ...")
    else:
        print("Real build folder not found, skipping real data test")


def main():
    """Run all tests."""
    print("Running tests for generate_dependencies.py")
    print("=" * 50)

    try:
        test_parsing_functions()
        test_full_processing()
        test_with_real_data()

        print("\n" + "=" * 50)
        print("All tests passed! ✓")
        return 0

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())