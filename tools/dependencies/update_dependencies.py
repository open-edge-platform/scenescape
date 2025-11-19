#!/usr/bin/env python3
"""
Script to update dependency list for the current version.

This script compares previous release dependencies with current build dependencies
and generates an updated dependency list with license information.
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass


@dataclass
class Dependency:
    """Represents a dependency with all its attributes."""
    image: str
    component: str
    origin: str
    license: str = ""
    distributed: str = ""
    comments: str = ""
    is_new: bool = False


def extract_component_name(component: str) -> str:
    """Extract component name without version for comparison."""
    # For APT packages: libxkbcommon-x11-0:amd64:1.6.0-1build1 -> libxkbcommon-x11-0
    # For pip packages: ConfigArgParse==1.7.1 -> ConfigArgParse
    if '==' in component:
        return component.split('==')[0]
    elif ':' in component:
        # For APT packages, take everything before the last colon (version part)
        parts = component.split(':')
        if len(parts) >= 3:  # package:arch:version
            return ':'.join(parts[:-1])  # package:arch
        else:
            return parts[0]  # just package name
    return component


def parse_csv_file(file_path: str) -> List[Dict[str, str]]:
    """Parse CSV file and return list of dictionaries."""
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        sys.exit(1)
    return data


def load_previous_dependencies(file_path: str) -> Dict[Tuple[str, str, str], Dependency]:
    """Load previous dependencies and create lookup dictionary."""
    deps = {}
    data = parse_csv_file(file_path)

    for row in data:
        dep = Dependency(
            image=row['Image'],
            component=row['Component'],
            origin=row['Origin'],
            license=row.get('License', ''),
            distributed=row.get('Distributed by you?', ''),
            comments=row.get('Comments', '')
        )
        # Key: (image, component, origin)
        key = (dep.image, dep.component, dep.origin)
        deps[key] = dep

    return deps


def load_current_dependencies(file_path: str) -> List[Dependency]:
    """Load current dependencies from generated CSV."""
    deps = []
    data = parse_csv_file(file_path)

    for row in data:
        dep = Dependency(
            image=row['Image'],
            component=row['Component'],
            origin=row['Origin']
        )
        deps.append(dep)

    return deps


def normalize_component_name(component: str) -> str:
    """Normalize component name for SBOM matching.

    Removes architecture specification from Ubuntu packages.
    Example: libpsl5:amd64:0.21.0-1.2build2 -> libpsl5:0.21.0-1.2build2
    """
    if ':' in component:
        parts = component.split(':')
        if len(parts) >= 3 and parts[1] in ['amd64', 'i386', 'arm64', 'all']:
            # Remove architecture part: package:arch:version -> package:version
            return f"{parts[0]}:{':'.join(parts[2:])}"
    return component


def load_sbom_data(sbom_folder_path: str) -> Dict[Tuple[str, str], str]:
    """Load SBOM data from all CSV files in the folder for license resolution."""
    sbom_data = {}
    sbom_folder = Path(sbom_folder_path)

    if not sbom_folder.exists():
        print(f"Warning: SBOM folder {sbom_folder_path} not found, skipping license resolution from SBOM")
        return sbom_data

    if not sbom_folder.is_dir():
        print(f"Warning: {sbom_folder_path} is not a directory, skipping license resolution from SBOM")
        return sbom_data

    # Find all CSV files in the SBOM folder
    csv_files = list(sbom_folder.glob('*.csv'))

    if not csv_files:
        print(f"Warning: No CSV files found in {sbom_folder_path}, skipping license resolution from SBOM")
        return sbom_data

    print(f"Loading SBOM data from {len(csv_files)} files...")

    for csv_file in csv_files:
        try:
            data = parse_csv_file(str(csv_file))

            for row in data:
                # Key: (image, normalized_component)
                image = row['Image']
                component = row['Component']
                normalized_component = normalize_component_name(component)

                key = (image, normalized_component)
                license_value = row.get('License', '')

                if license_value and license_value not in ['NOASSERTION', 'NO ASSERTION', 'LicenseRef-UNKNOWN']:
                    sbom_data[key] = license_value

        except Exception as e:
            print(f"Warning: Error reading SBOM file {csv_file}: {e}")
            continue

    return sbom_data


def load_image_list(image_list_path: str) -> Dict[str, Dict[str, str]]:
    """Load image list from CSV file."""
    image_data = {}

    try:
        data = parse_csv_file(image_list_path)
        for row in data:
            if row.get('Report Dependencies', '').upper() == 'Y':
                image_name = row['Image']
                image_data[image_name] = {
                    'dockerfile_path': row['Dockerfile Path'],
                    'published': row['Published'],
                    'dockerfile_name': row.get('Dockerfile Name', ''),
                    'comment': row.get('Comment', '')
                }
        return image_data
    except Exception as e:
        print(f"Error loading image list from {image_list_path}: {e}")
        sys.exit(1)


def extract_base_image_from_dockerfile(dockerfile_path: str) -> str:
    """Extract base image from Dockerfile.

    For multi-stage Dockerfiles, looks for runtime stage with pattern:
    FROM <base_image> AS <name>-runtime

    For single-stage Dockerfiles, returns the first FROM instruction.

    Handles variable substitution for ARG variables defined in the same Dockerfile.
    """
    try:
        with open(dockerfile_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse ARG instructions to build variable lookup
        variables = {}
        arg_pattern = r'^\s*ARG\s+([^=\s]+)(?:=(.+?))?\s*(?:#.*)?$'

        for line in content.splitlines():
            match = re.match(arg_pattern, line, re.IGNORECASE)
            if match:
                var_name = match.group(1)
                var_value = match.group(2) if match.group(2) else ""
                variables[var_name] = var_value

        # Pattern to match FROM instructions
        from_pattern = r'^\s*FROM\s+([^\s]+)(?:\s+AS\s+([^\s]+))?\s*(?:#.*)?$'

        # Find all FROM instructions
        from_instructions = []
        for line in content.splitlines():
            match = re.match(from_pattern, line, re.IGNORECASE)
            if match:
                base_image = match.group(1)
                stage_name = match.group(2) if match.group(2) else None

                # Resolve variables in base image
                resolved_base_image = resolve_dockerfile_variables(base_image, variables)

                from_instructions.append((resolved_base_image, stage_name, line.strip()))

        if not from_instructions:
            print(f"Warning: No FROM instruction found in {dockerfile_path}")
            return ""

        # Look for runtime stage first
        for base_image, stage_name, line in from_instructions:
            if stage_name and 'runtime' in stage_name.lower():
                return base_image

        # If no runtime stage found, return the last FROM instruction
        # (which is typically the final stage in multi-stage builds)
        return from_instructions[-1][0]

    except Exception as e:
        print(f"Warning: Error reading Dockerfile {dockerfile_path}: {e}")
        return ""


def resolve_dockerfile_variables(text: str, variables: Dict[str, str]) -> str:
    """Resolve Dockerfile variables in text using ${VAR} or $VAR syntax."""
    if not text or not variables:
        return text

    # Handle ${VAR_NAME} syntax first
    def replace_braced_var(match):
        var_name = match.group(1)
        if var_name in variables and variables[var_name]:
            return variables[var_name]
        return match.group(0)  # Return original if not found or empty

    # Handle $VAR_NAME syntax (but avoid replacing if it's part of ${VAR})
    def replace_simple_var(match):
        var_name = match.group(1)
        if var_name in variables and variables[var_name]:
            return variables[var_name]
        return match.group(0)  # Return original if not found or empty

    # First handle braced variables ${VAR}
    result = re.sub(r'\$\{([^}]+)\}', replace_braced_var, text)

    # Then handle simple variables $VAR, but only if the result doesn't contain ${ patterns
    # This is a simpler approach than complex negative lookbehind
    if '${' not in result:
        result = re.sub(r'\$([A-Za-z_][A-Za-z0-9_]*)', replace_simple_var, result)

    return result
class DependencyProcessor:
    """Processes dependencies according to the rules."""

    def __init__(self, image_data: Dict[str, Dict[str, str]] = None, show_new: bool = False):
        self.output_deps = []
        self.log_entries = []
        self.action_items = []
        self.image_data = image_data or {}
        self.show_new = show_new

    def get_distributed_value(self, image: str, prev_distributed: str = "") -> str:
        """Get the 'Distributed by you?' value based on image data."""
        if image in self.image_data:
            return self.image_data[image]['published']
        return prev_distributed

    def add_log_entry(self, entry: str):
        """Add entry to log."""
        self.log_entries.append(entry)

    def add_action_item(self, item: str):
        """Add item to action list."""
        if item not in self.action_items:
            self.action_items.append(item)

    def format_dependency_row(self, dep: Dependency) -> str:
        """Format dependency as CSV row for logging."""
        base_row = f"{dep.image},{dep.component},{dep.origin},{dep.license},{dep.distributed},{dep.comments}"
        if self.show_new:
            new_value = "Y" if dep.is_new else "N"
            return f"{base_row},{new_value}"
        return base_row

    def process_dependencies(self, previous_deps: Dict[Tuple[str, str, str], Dependency],
                           current_deps: List[Dependency],
                           sbom_data: Dict[Tuple[str, str], str]):
        """Process dependencies according to the rules."""

        # Create lookup dictionaries for different matching scenarios
        previous_by_exact = {}  # (image, component, origin)
        previous_by_image_name_origin = {}  # (image, component_name, origin) -> list of deps
        previous_by_name_origin = {}  # (component_name, origin) -> list of deps
        previous_images = set()

        for key, dep in previous_deps.items():
            previous_by_exact[key] = dep
            previous_images.add(dep.image)

            component_name = extract_component_name(dep.component)

            # Group by (image, component_name, origin)
            img_name_origin_key = (dep.image, component_name, dep.origin)
            if img_name_origin_key not in previous_by_image_name_origin:
                previous_by_image_name_origin[img_name_origin_key] = []
            previous_by_image_name_origin[img_name_origin_key].append(dep)

            # Group by (component_name, origin)
            name_origin_key = (component_name, dep.origin)
            if name_origin_key not in previous_by_name_origin:
                previous_by_name_origin[name_origin_key] = []
            previous_by_name_origin[name_origin_key].append(dep)

        # Track current images
        current_images = set(dep.image for dep in current_deps)

        # Track processed dependencies to avoid duplicates
        processed_current = set()

        # Process each current dependency
        for current_dep in current_deps:
            exact_key = (current_dep.image, current_dep.component, current_dep.origin)
            component_name = extract_component_name(current_dep.component)
            img_name_origin_key = (current_dep.image, component_name, current_dep.origin)
            name_origin_key = (component_name, current_dep.origin)

            processed = False

            # Rule 1: Exact match (image, component, origin)
            if exact_key in previous_by_exact:
                prev_dep = previous_by_exact[exact_key]
                new_dep = Dependency(
                    image=current_dep.image,
                    component=current_dep.component,
                    origin=current_dep.origin,
                    license=prev_dep.license,
                    distributed=self.get_distributed_value(current_dep.image, prev_dep.distributed),
                    comments=prev_dep.comments,
                    is_new=False
                )
                self.output_deps.append(new_dep)
                self.add_log_entry(f"COPIED_DEPENDENCY,{self.format_dependency_row(new_dep)}")
                processed_current.add(exact_key)
                processed = True

            # Rule 2: Same image and component name, but different version
            elif img_name_origin_key in previous_by_image_name_origin and not processed:
                # Find matching dependency with same image and component name
                candidates = previous_by_image_name_origin[img_name_origin_key]
                for prev_dep in candidates:
                    if exact_key not in processed_current:
                        new_dep = Dependency(
                            image=current_dep.image,
                            component=current_dep.component,
                            origin=current_dep.origin,
                            license=prev_dep.license,
                            distributed=self.get_distributed_value(current_dep.image, prev_dep.distributed),
                            comments=prev_dep.comments,
                            is_new=False
                        )
                        self.output_deps.append(new_dep)
                        self.add_log_entry(f"UPDATED_DEPENDENCY,{self.format_dependency_row(new_dep)}")
                        processed_current.add(exact_key)
                        processed = True
                        break

            # Rule 3: Same component name and origin, but different image
            elif name_origin_key in previous_by_name_origin and not processed:
                candidates = previous_by_name_origin[name_origin_key]
                for prev_dep in candidates:
                    if prev_dep.image != current_dep.image and exact_key not in processed_current:
                        new_dep = Dependency(
                            image=current_dep.image,
                            component=current_dep.component,
                            origin=current_dep.origin,
                            license=f"?{prev_dep.license}",
                            distributed=self.get_distributed_value(current_dep.image, prev_dep.distributed),
                            comments=f"?{prev_dep.comments}",
                            is_new=True
                        )
                        self.output_deps.append(new_dep)
                        self.add_log_entry(f"REUSED_DEPENDENCY from {prev_dep.image},{self.format_dependency_row(new_dep)}")
                        self.add_action_item("review dependencies reused across images (review license, distributor, usage information) where '?' is added before the automatically updated value")
                        processed_current.add(exact_key)
                        processed = True
                        break

            # Rule 5: New dependency
            if not processed:
                new_dep = Dependency(
                    image=current_dep.image,
                    component=current_dep.component,
                    origin=current_dep.origin,
                    license="?",
                    distributed=self.get_distributed_value(current_dep.image),
                    comments="?",
                    is_new=True
                )
                self.output_deps.append(new_dep)
                self.add_log_entry(f"ADDED_DEPENDENCY,{self.format_dependency_row(new_dep)}")
                self.add_action_item("fill in placeholders '?' (license, distributor, usage) for new dependencies")
                processed_current.add(exact_key)

        # Rule 4: Images not found in current
        missing_images = previous_images - current_images
        for image in missing_images:
            for key, prev_dep in previous_deps.items():
                if prev_dep.image == image:
                    self.add_log_entry(f"IMAGE_NOT_FOUND {image},{self.format_dependency_row(prev_dep)}")
                    self.add_action_item("double check not found images (not updated .csv from previous release?)")

        # Rule 6: Dependencies removed (exist in previous but not in current)
        for key, prev_dep in previous_deps.items():
            component_name = extract_component_name(prev_dep.component)
            name_origin_key = (component_name, prev_dep.origin)

            # Check if this (component_name, origin) exists in current dependencies
            found_in_current = any(
                extract_component_name(curr_dep.component) == component_name and curr_dep.origin == prev_dep.origin
                for curr_dep in current_deps
            )

            if not found_in_current:
                self.add_log_entry(f"REMOVED_DEPENDENCY,{self.format_dependency_row(prev_dep)}")

        # Final step: Resolve licenses from SBOM
        self.resolve_licenses_from_sbom(sbom_data)

        # Add base image dependencies
        self.add_base_image_dependencies()

    def add_base_image_dependencies(self):
        """Add base image dependencies for each image in the image list."""
        for image_name, image_info in self.image_data.items():
            dockerfile_path = image_info['dockerfile_path']

            # Extract base image from Dockerfile
            base_image = extract_base_image_from_dockerfile(dockerfile_path)

            if base_image:
                # Create base image dependency
                base_dep = Dependency(
                    image=image_name,
                    component=base_image,
                    origin="Ubuntu",  # As specified in requirements
                    license="collection of licenses",  # As specified in requirements
                    distributed="N",  # As specified in requirements
                    comments="base image"  # As specified in requirements
                )

                self.output_deps.append(base_dep)
                self.add_log_entry(f"BASE_IMAGE_DEPENDENCY,{self.format_dependency_row(base_dep)}")
            else:
                print(f"Warning: Could not extract base image for {image_name} from {dockerfile_path}")

    def resolve_licenses_from_sbom(self, sbom_data: Dict[Tuple[str, str], str]):
        """Resolve licenses for dependencies with '?' license using SBOM data."""
        for dep in self.output_deps:
            if dep.license == "?":
                # Try both original and normalized component names for matching
                normalized_component = normalize_component_name(dep.component)

                sbom_keys_to_try = [
                    (dep.image, dep.component),          # Try exact match first
                    (dep.image, normalized_component)     # Try normalized match
                ]

                license_found = False
                for sbom_key in sbom_keys_to_try:
                    if sbom_key in sbom_data:
                        dep.license = sbom_data[sbom_key]
                        self.add_log_entry(f"LICENCE_IDENTIFIED,{self.format_dependency_row(dep)}")
                        self.add_action_item("review resolved license information")
                        license_found = True
                        break

                if not license_found:
                    # Debug info for unmatched dependencies
                    pass  # We could add debug logging here if needed


def write_output_csv(dependencies: List[Dependency], output_file: str, show_new: bool = False):
    """Write dependencies to output CSV file."""
    # Sort by image, origin, component name as specified
    dependencies.sort(key=lambda d: (d.image, d.origin, extract_component_name(d.component)))

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Write header
        header = ['Image', 'Component', 'Origin', 'License', 'Distributed by you?', 'Comments']
        if show_new:
            header.append('New')
        writer.writerow(header)

        # Write dependencies
        for dep in dependencies:
            row = [dep.image, dep.component, dep.origin, dep.license, dep.distributed, dep.comments]
            if show_new:
                row.append('Y' if dep.is_new else 'N')
            writer.writerow(row)


def write_log_file(log_entries: List[str], log_file: str):
    """Write log entries to log file."""
    with open(log_file, 'w', encoding='utf-8') as f:
        for entry in log_entries:
            f.write(entry + '\n')


def print_action_list(action_items: List[str]):
    """Print action list for user."""
    print("\nAction list for user:")
    for i, item in enumerate(action_items, 1):
        print(f"{i}. {item}")

    print("\nAdditional actions:")
    print("- identify and manually add any missed dependencies (JavaScript, dependencies installed as prerequisites etc.)")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Update dependency list for the current version"
    )
    parser.add_argument(
        '--from',
        dest='previous_file',
        required=True,
        help='Previous release CSV file with dependencies and license information'
    )
    parser.add_argument(
        '--deps',
        required=True,
        help='Current dependencies CSV file generated from Dockerfiles'
    )
    parser.add_argument(
        '--sbom',
        required=True,
        help='SBOM folder containing CSV files with license information'
    )
    parser.add_argument(
        '--image-list',
        required=True,
        help='CSV file with image list containing Dockerfile paths and published status'
    )
    parser.add_argument(
        '--output',
        default='updated-dependencies.csv',
        help='Output CSV file name (default: updated-dependencies.csv)'
    )
    parser.add_argument(
        '--show-new',
        action='store_true',
        help='Add "New" column to output CSV to indicate new dependencies'
    )

    args = parser.parse_args()

    # Validate input files
    for file_path in [args.previous_file, args.deps, args.image_list]:
        if not Path(file_path).exists():
            print(f"Error: File {file_path} not found")
            sys.exit(1)

    print("Loading image list...")
    image_data = load_image_list(args.image_list)
    print(f"Loaded {len(image_data)} images for processing")

    print("Loading previous dependencies...")
    previous_deps = load_previous_dependencies(args.previous_file)
    print(f"Loaded {len(previous_deps)} previous dependencies")

    print("Loading current dependencies...")
    current_deps = load_current_dependencies(args.deps)
    print(f"Loaded {len(current_deps)} current dependencies")

    print("Loading SBOM data...")
    sbom_data = load_sbom_data(args.sbom)
    print(f"Loaded {len(sbom_data)} SBOM entries from folder")

    print("Processing dependencies...")
    processor = DependencyProcessor(image_data, args.show_new)
    processor.process_dependencies(previous_deps, current_deps, sbom_data)

    # Write outputs
    output_file = args.output
    log_file = output_file.replace('.csv', '-log.txt')

    print(f"Writing output to {output_file}...")
    write_output_csv(processor.output_deps, output_file, args.show_new)

    print(f"Writing log to {log_file}...")
    write_log_file(processor.log_entries, log_file)

    print(f"\nProcessing complete:")
    print(f"- Output dependencies: {len(processor.output_deps)}")
    print(f"- Log entries: {len(processor.log_entries)}")
    print(f"- Output file: {output_file}")
    print(f"- Log file: {log_file}")

    # Print action list
    print_action_list(processor.action_items)

    return 0


if __name__ == "__main__":
    exit(main())