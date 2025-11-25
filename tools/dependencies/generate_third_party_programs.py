#!/usr/bin/env python3
"""
Generate third-party programs file from reviewed dependency list CSV.

This script takes a completed dependencies CSV file (with all licenses identified)
and generates a third-party programs file listing all dependencies and their
license texts to satisfy requirements imposed by inbound licenses.
"""

import argparse
import csv
from collections import defaultdict
import requests
import os
import sys
from pathlib import Path


def get_license_url(license_name):
    """Get SPDX license URL for a given license name."""
    spdx_base = "https://spdx.org/licenses/"

    # Map common license names to SPDX identifiers
    custom_map = {
        "AFL-2.1 License": spdx_base + "AFL-2.1.txt",
        "Apache-2.0": spdx_base + "Apache-2.0.txt",
        "Artistic License": spdx_base + "Artistic-2.0.txt",
        "Artistic License 1.0": spdx_base + "Artistic-1.0.txt",
        "BSD License": spdx_base + "BSD-3-Clause.txt",
        "BSD-2-Clause": spdx_base + "BSD-2-Clause.txt",
        "BSD-3-Clause": spdx_base + "BSD-3-Clause.txt",
        "EPL-1.0": spdx_base + "EPL-1.0.txt",
        "EPL-2.0": spdx_base + "EPL-2.0.txt",
        "FTL": spdx_base + "FTL.txt",
        "GPL-1.0": spdx_base + "GPL-1.0-only.txt",
        "GPL-2.0": spdx_base + "GPL-2.0-only.txt",
        "GPL-3.0": spdx_base + "GPL-3.0-only.txt",
        "HPND": spdx_base + "HPND.txt",
        "ICU License": spdx_base + "ICU.txt",
        "ISC": spdx_base + "ISC.txt",
        "ISC License": spdx_base + "ISC.txt",
        "JBIG License": spdx_base + "JBIG.txt",
        "LGPL": spdx_base + "LGPL-2.1-only.txt",
        "LGPL-2.0": spdx_base + "LGPL-2.0-only.txt",
        "LGPL-2.1": spdx_base + "LGPL-2.1-only.txt",
        "LGPL-3.0": spdx_base + "LGPL-3.0-only.txt",
        "libpng License": spdx_base + "Libpng.txt",
        "MIT": spdx_base + "MIT.txt",
        "MPL-1.1": spdx_base + "MPL-1.1.txt",
        "MPL-2.0": spdx_base + "MPL-2.0.txt",
        "OpenLDAP Public License": spdx_base + "OLDAP-2.8.txt",
        "PIL": spdx_base + "HPND.txt",  # PIL uses HPND
        "PostgreSQL": spdx_base + "PostgreSQL.txt",
        "PSF": spdx_base + "Python-2.0.txt",
        "Qhull License": spdx_base + "Qhull.txt",
        "SIL Open Font License": spdx_base + "OFL-1.1.txt",
        "Unlicense": spdx_base + "Unlicense.txt",
        "X11": spdx_base + "X11.txt",
    }
    return custom_map.get(license_name, "")


def is_special_license(license_name):
    """Check if this is a special license type that doesn't require license text."""
    special_licenses = {
        "Public Domain",
        "collection of licenses"
    }
    return license_name in special_licenses


def sanitize_filename(name):
    """Sanitize a filename to be safe for filesystem use."""
    return name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_").replace("\n", "_")


def download_license_text(license_name, license_sources, failed_licenses, licenses_dir, special_licenses_skipped):
    """Download or read license text for a given license."""
    # Handle special licenses that don't require license text
    if is_special_license(license_name):
        license_sources[license_name] = "Special license (no text required)"
        special_licenses_skipped.add(license_name)
        if license_name == "Public Domain":
            return "This software is in the Public Domain and is not subject to copyright restrictions."
        elif license_name == "collection of licenses":
            return "This component contains a collection of different licenses. Please refer to the original source for specific license terms."
        else:
            return f"Special license type: {license_name}"

    url = get_license_url(license_name)
    if url:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                license_sources[license_name] = url
                return resp.text
        except Exception:
            pass

    # Try local file
    local_filename = os.path.join(licenses_dir, sanitize_filename(license_name) + ".txt")
    if os.path.isfile(local_filename):
        try:
            with open(local_filename, "r", encoding="utf-8") as lf:
                license_sources[license_name] = local_filename
                return lf.read()
        except Exception as e:
            failed_licenses.append(license_name)
            license_sources[license_name] = None
            return f"[Error reading local license file for {license_name}: {e}]"

    failed_licenses.append(license_name)
    license_sources[license_name] = None
    return f"[No license text available for {license_name}]"


def process_dependencies(input_file, output_file, preamble_file, licenses_dir):
    """Process dependencies CSV and generate third-party programs file."""
    components = []
    licenses = set()
    license_to_components = defaultdict(list)
    failed_licenses = []
    special_licenses_skipped = set()
    license_sources = {}  # license_name -> source (url, file, or None)

    # Read dependencies CSV
    with open(input_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            component = row["Component"].strip()
            license_ = row["License"].strip()
            components.append((component, license_))
            if license_:
                # Split multiple licenses
                for lic in [l.strip() for l in license_.replace(" and ", ",").replace(" or ", ",").replace(" OR ", ",").split(",")]:
                    if lic:
                        licenses.add(lic)
                        license_to_components[lic].append(component)

    # Sort licenses and components
    licenses_sorted = sorted(licenses, key=lambda x: x.lower())
    for lic in licenses_sorted:
        license_to_components[lic] = sorted(set(license_to_components[lic]), key=lambda x: x.lower())

    # Read preamble
    preamble = ""
    if os.path.isfile(preamble_file):
        with open(preamble_file, "r", encoding="utf-8") as pf:
            preamble = pf.read().rstrip() + "\n"

    # Generate output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(preamble)
        for idx, lic in enumerate(licenses_sorted, 1):
            f.write("\n\n")
            f.write("-------------------------------------------------------------\n")
            f.write(f"{idx}. Software released under the license {lic}:\n")
            for comp in license_to_components[lic]:
                f.write(f"    {comp}\n")
            f.write("\n")
            license_text = download_license_text(lic, license_sources, failed_licenses, licenses_dir, special_licenses_skipped)
            f.write(license_text.strip() + "\n")

    # Print summary
    print(f"Processed {len(components)} total components")
    print(f"Found {len(licenses_sorted)} unique licenses")

    print("\nUnique licenses used (with source):")
    for lic in licenses_sorted:
        src = license_sources.get(lic)
        if src is None:
            src_str = "None"
        elif src.startswith("http"):
            src_str = f"URL: {src}"
        else:
            src_str = f"File: {src}"
        print(f" - {lic} [{src_str}]")

    if special_licenses_skipped:
        print("\nSpecial licenses (no license text required):")
        for lic in sorted(special_licenses_skipped):
            print(f" - {lic}")
        print("\nNote: These special license types are included in the output with explanatory text only.")

    if failed_licenses:
        print("\nFailed to obtain license text for the following licenses:")
        for lic in sorted(set(failed_licenses)):
            print(f" - {lic}")
        print("\nNote: Review not found licenses and update the local licenses directory accordingly.")

    print(f"\nGenerated {output_file}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate third-party programs file from reviewed dependency list CSV"
    )
    parser.add_argument(
        "input_file",
        help="Input CSV file with dependencies (must have Component and License columns)"
    )
    parser.add_argument(
        "-o", "--output",
        default="third-party-programs.txt",
        help="Output third-party programs file (default: third-party-programs.txt)"
    )
    parser.add_argument(
        "--preamble",
        default="licenses/preamble.txt",
        help="Preamble text file (default: licenses/preamble.txt)"
    )
    parser.add_argument(
        "--licenses-dir",
        default="licenses",
        help="Directory containing local license files (default: licenses)"
    )

    args = parser.parse_args()

    # Validate input file
    if not Path(args.input_file).exists():
        print(f"Error: Input file {args.input_file} not found")
        sys.exit(1)

    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Process dependencies
    process_dependencies(args.input_file, args.output, args.preamble, args.licenses_dir)


if __name__ == "__main__":
    main()
