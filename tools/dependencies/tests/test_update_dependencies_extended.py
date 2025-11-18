#!/usr/bin/env python3
"""
Extended test for update_dependencies.py script with image list functionality.
"""

import csv
import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def create_test_files():
    """Create test files for the extended functionality."""

    # Create temporary directory
    test_dir = Path(tempfile.mkdtemp())

    # Previous dependencies CSV
    prev_deps = [
        ['Image', 'Component', 'Origin', 'License', 'Distributed by you?', 'Comments'],
        ['test-app', 'libtest==1.0.0', 'Ubuntu', 'GPL-2.0', 'Y', 'testing'],
        ['test-web', 'nginx==1.20.1', 'Ubuntu', 'BSD-2-Clause', 'N', 'web server']
    ]
    prev_file = test_dir / 'previous.csv'
    with open(prev_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(prev_deps)

    # Current dependencies CSV
    curr_deps = [
        ['Image', 'Component', 'Origin'],
        ['test-app', 'libtest==1.1.0', 'Ubuntu'],
        ['test-app', 'newlib==2.0.0', 'Ubuntu'],
        ['test-web', 'nginx==1.21.0', 'Ubuntu'],
    ]
    curr_file = test_dir / 'current.csv'
    with open(curr_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(curr_deps)

    # SBOM folder with CSV files
    sbom_dir = test_dir / 'sboms'
    sbom_dir.mkdir()

    # SBOM for test-app
    sbom_app = [
        ['Image', 'Component', 'License'],
        ['test-app', 'libtest', 'GPL-3.0'],
        ['test-app', 'newlib', 'MIT']
    ]
    with open(sbom_dir / 'test-app-sbom.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(sbom_app)

    # SBOM for test-web
    sbom_web = [
        ['Image', 'Component', 'License'],
        ['test-web', 'nginx', 'BSD-2-Clause-Updated']
    ]
    with open(sbom_dir / 'test-web-sbom.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(sbom_web)

    # Image list CSV
    image_list = [
        ['Image', 'Dockerfile Path', 'Dockerfile Name', 'Report Dependencies', 'Published', 'Comment'],
        ['test-app', str(test_dir / 'test-app' / 'Dockerfile'), 'Dockerfile-app', 'Y', 'Y', 'Published app'],
        ['test-web', str(test_dir / 'test-web' / 'Dockerfile'), 'Dockerfile-web', 'Y', 'N', 'Internal web'],
        ['test-skip', str(test_dir / 'test-skip' / 'Dockerfile'), 'Dockerfile-skip', 'N', 'Y', 'Skipped']
    ]
    image_file = test_dir / 'images.csv'
    with open(image_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(image_list)

    # Create test Dockerfiles
    app_dir = test_dir / 'test-app'
    app_dir.mkdir(parents=True)
    with open(app_dir / 'Dockerfile', 'w') as f:
        f.write('''# Test Dockerfile for app
FROM ubuntu:22.04 AS test-app-builder
RUN apt-get update

FROM ubuntu:20.04 AS test-app-runtime
COPY --from=test-app-builder /app /app
''')

    web_dir = test_dir / 'test-web'
    web_dir.mkdir(parents=True)
    with open(web_dir / 'Dockerfile', 'w') as f:
        f.write('''# Single stage Dockerfile
FROM nginx:1.21-alpine
COPY config /etc/nginx
''')

    skip_dir = test_dir / 'test-skip'
    skip_dir.mkdir(parents=True)
    with open(skip_dir / 'Dockerfile', 'w') as f:
        f.write('''# Skipped Dockerfile
FROM alpine:latest
RUN echo "skipped"
''')

    return {
        'test_dir': test_dir,
        'prev_file': prev_file,
        'curr_file': curr_file,
        'sbom_dir': sbom_dir,
        'image_file': image_file,
        'output_file': test_dir / 'output.csv',
        'log_file': test_dir / 'output-log.txt'
    }


def run_script(files):
    """Run the update-dependencies script with test files."""
    script_path = Path(__file__).parent.parent / 'update_dependencies.py'

    cmd = [
        'python3', str(script_path),
        '--from', str(files['prev_file']),
        '--deps', str(files['curr_file']),
        '--sbom', str(files['sbom_dir']),
        '--image-list', str(files['image_file']),
        '--output', str(files['output_file'])
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=files['test_dir'])
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running script: {e}")
        return False


def verify_output(files):
    """Verify the output contains expected results."""
    output_file = files['output_file']

    if not output_file.exists():
        print("❌ Output file not created")
        return False

    # Read output CSV
    dependencies = []
    with open(output_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        dependencies = list(reader)

    print(f"✓ Found {len(dependencies)} dependencies in output")

    # Debug: Print all dependencies
    print("Debug: All dependencies found:")
    for i, dep in enumerate(dependencies):
        print(f"  {i+1}. {dep['Image']}: {dep['Component']} -> Distributed: {dep['Distributed by you?']}")

    # Verify distributed field is set correctly
    test_cases = [
        # Image published=Y should have distributed=Y
        {'image': 'test-app', 'distributed_expected': 'Y'},
        # Image published=N should have distributed=N
        {'image': 'test-web', 'distributed_expected': 'N'}
    ]

    distributed_ok = True
    for case in test_cases:
        # Only check non-base-image dependencies
        image_deps = [d for d in dependencies if d['Image'] == case['image'] and d['Comments'] != 'base image']
        for dep in image_deps:
            if not dep['Distributed by you?'].startswith(case['distributed_expected']):
                print(f"❌ Wrong distributed value for {case['image']}: expected {case['distributed_expected']}, got {dep['Distributed by you?']}")
                distributed_ok = False

    if distributed_ok:
        print("✓ Distributed field correctly set based on Published status")

    # Verify base images are added
    base_images = [d for d in dependencies if d['Comments'] == 'base image']
    expected_base_images = 2  # test-app and test-web

    if len(base_images) == expected_base_images:
        print("✓ Base image dependencies added correctly")
        for base_dep in base_images:
            print(f"  - {base_dep['Image']}: {base_dep['Component']}")
    else:
        print(f"❌ Expected {expected_base_images} base images, found {len(base_images)}")
        return False

    # Verify base image properties
    base_image_ok = True
    for base_dep in base_images:
        if base_dep['Origin'] != 'Ubuntu':
            print(f"❌ Base image origin should be Ubuntu, got {base_dep['Origin']}")
            base_image_ok = False
        if base_dep['License'] != 'collection of licenses':
            print(f"❌ Base image license should be 'collection of licenses', got {base_dep['License']}")
            base_image_ok = False
        if base_dep['Distributed by you?'] != 'N':
            print(f"❌ Base image distributed should be N, got {base_dep['Distributed by you?']}")
            base_image_ok = False

    if base_image_ok:
        print("✓ Base image properties are correct")

    return distributed_ok and base_image_ok


def main():
    """Main test function."""
    print("🧪 Testing update_dependencies.py with image list functionality...")

    # Create test files
    print("📁 Creating test files...")
    files = create_test_files()

    try:
        # Run the script
        print("🚀 Running script...")
        success = run_script(files)

        if not success:
            print("❌ Script execution failed")
            return 1

        print("✓ Script executed successfully")

        # Verify output
        print("🔍 Verifying output...")
        if verify_output(files):
            print("✅ All tests passed!")
            return 0
        else:
            print("❌ Test verification failed")
            return 1

    finally:
        # Cleanup
        shutil.rmtree(files['test_dir'])
        print("🧹 Cleaned up test files")


if __name__ == "__main__":
    exit(main())