#!/usr/bin/env python3
"""
Script to generate a CSV file with all dependencies from build logs.

This script scans a build folder for dependency files and creates a unified CSV
with all dependencies across all images.
"""

import argparse
import csv
import os
import re
from pathlib import Path
from typing import List, Tuple


def extract_image_name(filename: str, suffix: str) -> str:
    """Extract image name from filename by removing the suffix."""
    return filename.replace(suffix, "")


def parse_apt_dependency(line: str) -> str:
    """
    Parse APT dependency line and return formatted component name.
    
    Example input: "libxkbcommon-x11-0:amd64 1.6.0-1build1 amd64"
    Example output: "libxkbcommon-x11-0:amd64:1.6.0-1build1"
    """
    parts = line.strip().split()
    if len(parts) >= 2:
        package_name = parts[0]
        version = parts[1]
        return f"{package_name}:{version}"
    return line.strip()


def parse_pip_dependency(line: str) -> str:
    """
    Parse pip dependency line and return as-is.
    
    Example input: "ConfigArgParse==1.7.1"
    Example output: "ConfigArgParse==1.7.1"
    """
    return line.strip()


def process_dependency_files(build_folder: str) -> List[Tuple[str, str, str]]:
    """
    Process all dependency files in the build folder.
    
    Returns a list of tuples: (image_name, component, origin)
    """
    dependencies = []
    build_path = Path(build_folder)
    
    if not build_path.exists():
        raise FileNotFoundError(f"Build folder not found: {build_folder}")
    
    # Process APT dependency files
    apt_pattern = "*-apt-deps.txt"
    for apt_file in build_path.glob(apt_pattern):
        image_name = extract_image_name(apt_file.name, "-apt-deps.txt")
        
        try:
            with open(apt_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:  # Skip empty lines
                        try:
                            component = parse_apt_dependency(line)
                            dependencies.append((image_name, component, "Ubuntu"))
                        except Exception as e:
                            print(f"Warning: Error parsing line {line_num} in {apt_file}: {e}")
                            print(f"  Line content: {line}")
        except Exception as e:
            print(f"Error reading file {apt_file}: {e}")
    
    # Process pip dependency files
    pip_pattern = "*-pip-deps.txt"
    for pip_file in build_path.glob(pip_pattern):
        image_name = extract_image_name(pip_file.name, "-pip-deps.txt")
        
        try:
            with open(pip_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:  # Skip empty lines
                        try:
                            component = parse_pip_dependency(line)
                            dependencies.append((image_name, component, "pypi"))
                        except Exception as e:
                            print(f"Warning: Error parsing line {line_num} in {pip_file}: {e}")
                            print(f"  Line content: {line}")
        except Exception as e:
            print(f"Error reading file {pip_file}: {e}")
    
    return dependencies


def write_csv(dependencies: List[Tuple[str, str, str]], output_file: str):
    """Write dependencies to CSV file."""
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow(['Image', 'Component', 'Origin'])
        
        # Write dependencies
        for image, component, origin in dependencies:
            writer.writerow([image, component, origin])


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate CSV file with all dependencies from build folder"
    )
    parser.add_argument(
        "build_folder",
        help="Path to the build folder containing dependency files"
    )
    parser.add_argument(
        "-o", "--output",
        default="dependencies.csv",
        help="Output CSV file name (default: dependencies.csv)"
    )
    
    args = parser.parse_args()
    
    try:
        print(f"Processing dependency files in: {args.build_folder}")
        dependencies = process_dependency_files(args.build_folder)
        
        print(f"Found {len(dependencies)} dependencies")
        
        # Sort dependencies by image name, then by component name
        dependencies.sort(key=lambda x: (x[0], x[1]))
        
        write_csv(dependencies, args.output)
        print(f"Dependencies written to: {args.output}")
        
        # Print summary
        images = set(dep[0] for dep in dependencies)
        print(f"Processed {len(images)} images: {', '.join(sorted(images))}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())