#!/usr/bin/env python3
"""
Test script for update_dependencies.py
"""

import tempfile
import subprocess
import csv
from pathlib import Path

def run_script_test():
    """Run comprehensive test with known data."""

    # Create test data
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create comprehensive test previous file
        previous_file = temp_path / "previous.csv"
        with open(previous_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Image', 'Component', 'Origin', 'License', 'Distributed by you?', 'Comments'])
            writer.writerow(['image1', 'pkg-exact==1.0.0', 'pypi', 'MIT', 'Y', 'exact match test'])
            writer.writerow(['image1', 'pkg-update==1.0.0', 'pypi', 'Apache-2.0', 'Y', 'version update test'])
            writer.writerow(['image1', 'pkg-reuse==1.0.0', 'pypi', 'BSD-3-Clause', 'Y', 'reuse test'])
            writer.writerow(['old-image', 'pkg-removed==1.0.0', 'pypi', 'GPL-3.0', 'Y', 'will be removed'])
            writer.writerow(['image2', 'pkg-cross==1.0.0', 'pypi', 'LGPL-2.1', 'Y', 'cross image'])

        # Create current dependencies
        current_file = temp_path / "current.csv"
        with open(current_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Image', 'Component', 'Origin'])
            writer.writerow(['image1', 'pkg-exact==1.0.0', 'pypi'])  # exact match
            writer.writerow(['image1', 'pkg-update==2.0.0', 'pypi'])  # version update
            writer.writerow(['image1', 'pkg-new==1.0.0', 'pypi'])    # completely new
            writer.writerow(['image2', 'pkg-reuse==1.0.0', 'pypi'])  # reused from image1
            writer.writerow(['image3', 'pkg-cross==2.0.0', 'pypi'])  # moved from image2

        # Create SBOM folder with data
        sbom_dir = temp_path / "sboms"
        sbom_dir.mkdir()
        sbom_file = sbom_dir / "image1.csv"
        with open(sbom_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Image', 'Component', 'License'])
            writer.writerow(['image1', 'pkg-new==1.0.0', 'ISC'])  # license resolved

        # Create image list file
        image_list_file = temp_path / "images.csv"
        with open(image_list_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Image', 'Dockerfile Path', 'Dockerfile Name', 'Report Dependencies', 'Published', 'Comment'])
            writer.writerow(['image1', '/dev/null', 'Dockerfile-1', 'Y', 'Y', 'Test image 1'])
            writer.writerow(['image2', '/dev/null', 'Dockerfile-2', 'Y', 'N', 'Test image 2'])
            writer.writerow(['old-image', '/dev/null', 'Dockerfile-old', 'Y', 'Y', 'Test old image'])

        # Run the script
        script_path = "/home/labrat/tdorau/repos/scenescape/tools/dependencies/update_dependencies.py"
        output_file = temp_path / "output.csv"

        result = subprocess.run([
            'python3', script_path,
            '--from', str(previous_file),
            '--deps', str(current_file),
            '--sbom', str(sbom_dir),
            '--image-list', str(image_list_file),
            '--output', str(output_file)
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Script failed: {result.stderr}")
            return False

        # Read and verify output
        output_data = []
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            output_data = list(reader)

        # Read log
        log_file = str(output_file).replace('.csv', '-log.txt')
        with open(log_file, 'r') as f:
            log_content = f.read()

        print("Test Results:")
        print("=============")

        print(f"\nOutput dependencies ({len(output_data)}):")
        for dep in output_data:
            print(f"  {dep['Image']},{dep['Component']},{dep['License']}")

        print(f"\nLog entries:")
        for line in log_content.strip().split('\n'):
            if line.strip():
                print(f"  {line}")

        # Verify expected results
        expected_results = {
            'exact_match': False,
            'version_update': False,
            'reuse_across_images': False,
            'license_from_sbom': False,
            'new_dependency': False,
            'moved_dependency': False
        }

        # Check output
        for dep in output_data:
            if dep['Component'] == 'pkg-exact==1.0.0' and dep['License'] == 'MIT':
                expected_results['exact_match'] = True
            elif dep['Component'] == 'pkg-update==2.0.0' and dep['License'] == 'Apache-2.0':
                expected_results['version_update'] = True
            elif dep['Component'] == 'pkg-reuse==1.0.0' and dep['Image'] == 'image2' and dep['License'] == '?BSD-3-Clause':
                expected_results['reuse_across_images'] = True
            elif dep['Component'] == 'pkg-new==1.0.0' and dep['License'] == 'ISC':
                expected_results['license_from_sbom'] = True
                expected_results['new_dependency'] = True  # This was added as new and license resolved
            elif dep['Component'] == 'pkg-cross==2.0.0' and dep['Image'] == 'image3':
                expected_results['moved_dependency'] = True

        # Check log entries
        if 'COPIED_DEPENDENCY' in log_content:
            print("✓ COPIED_DEPENDENCY found")
        if 'UPDATED_DEPENDENCY' in log_content:
            print("✓ UPDATED_DEPENDENCY found")
        if 'REUSED_DEPENDENCY' in log_content:
            print("✓ REUSED_DEPENDENCY found")
        if 'ADDED_DEPENDENCY' in log_content:
            print("✓ ADDED_DEPENDENCY found")
        if 'REMOVED_DEPENDENCY' in log_content:
            print("✓ REMOVED_DEPENDENCY found")
        if 'IMAGE_NOT_FOUND' in log_content:
            print("✓ IMAGE_NOT_FOUND found")
        if 'LICENCE_IDENTIFIED' in log_content:
            print("✓ LICENCE_IDENTIFIED found")

        print(f"\nValidation:")
        for check, passed in expected_results.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}")

        return all(expected_results.values())

if __name__ == "__main__":
    print("Running comprehensive test for update_dependencies.py")
    success = run_script_test()
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Some tests failed!")
    exit(0 if success else 1)