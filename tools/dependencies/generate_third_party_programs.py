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
import re

# Global cache for license texts to avoid redundant downloads
_license_text_cache = {}


def get_license_url(license_name):
    """Get SPDX license URL for a given license name."""
    # Primary SPDX license repository
    spdx_base = "https://raw.githubusercontent.com/spdx/license-list-data/refs/heads/main/text/"
    # Fallback to spdx.org (kept for backward compatibility)
    spdx_org_base = "https://spdx.org/licenses/"

    # Map license names that require custom SPDX identifier mapping
    # Only licenses that cannot be auto-discovered are included here
    custom_map = {
        # Version mappings where the license name doesn't include version
        "Artistic License": spdx_base + "Artistic-2.0.txt",
        "Artistic License 1.0": spdx_base + "Artistic-1.0.txt",
        "BSD License": spdx_base + "BSD-3-Clause.txt",  # Generic BSD maps to 3-clause

        # GPL/LGPL licenses that need -only suffix
        "GPL-1.0": spdx_base + "GPL-1.0-only.txt",
        "GPL-2.0": spdx_base + "GPL-2.0-only.txt",
        "GPL-2.0-or-later": spdx_base + "GPL-2.0-or-later.txt",
        "GPL-3.0": spdx_base + "GPL-3.0-only.txt",
        "LGPL": spdx_base + "LGPL-2.1-only.txt",  # Default LGPL version
        "LGPL-2.0": spdx_base + "LGPL-2.0-only.txt",
        "LGPL-2.1": spdx_base + "LGPL-2.1-only.txt",
        "LGPL-3.0": spdx_base + "LGPL-3.0-only.txt",

        # License names that map to different SPDX identifiers
        "libpng License": spdx_base + "Libpng.txt",  # Case change required
        "OpenLDAP Public License": spdx_base + "OLDAP-2.8.txt",  # Completely different name
        "PIL": spdx_base + "HPND.txt",  # PIL uses HPND license
        "PSF": spdx_base + "Python-2.0.txt",  # PSF -> Python-2.0
        "SIL Open Font License": spdx_base + "OFL-1.1.txt",  # Completely different name
    }    # First, try the custom mapping
    if license_name in custom_map:
        return custom_map[license_name]

    # Auto-discovery: try to construct URL from license name
    # Replace common patterns to match SPDX naming convention
    spdx_name = license_name.strip()

    # Try direct match first
    candidate_urls = [
        spdx_base + spdx_name + ".txt",
    ]

    # Try with common transformations
    if not spdx_name.endswith(".txt"):
        # For GPL/LGPL licenses, try adding -only suffix
        if spdx_name in ["GPL-1.0", "GPL-2.0", "GPL-3.0", "LGPL-2.0", "LGPL-2.1", "LGPL-3.0"]:
            candidate_urls.append(spdx_base + spdx_name + "-only.txt")

        # Try common license name patterns
        candidate_urls.extend([
            spdx_base + spdx_name.replace(" ", "-") + ".txt",
            spdx_base + spdx_name.replace(" License", "") + ".txt",
            spdx_base + spdx_name.replace("License", "").strip() + ".txt",
        ])

    # Test each candidate URL
    for url in candidate_urls:
        try:
            import requests
            resp = requests.head(url, timeout=5)  # Use HEAD to avoid downloading full content
            if resp.status_code == 200:
                return url
        except Exception:
            continue

    return ""


def parse_license_expression(license_expr):
    """
    Parse SPDX license expression and return structured data.

    Handles expressions with AND, OR operators and parentheses.
    Examples:
        - "MIT" -> {"type": "single", "license": "MIT"}
        - "MIT AND Apache-2.0" -> {"type": "and", "licenses": ["MIT", "Apache-2.0"]}
        - "MIT OR Apache-2.0" -> {"type": "or", "licenses": ["MIT", "Apache-2.0"]}
        - "(MIT AND Python-2.0)" -> {"type": "and", "licenses": ["MIT", "Python-2.0"]}

    Returns:
        dict: Parsed expression structure
    """
    if not license_expr or not license_expr.strip():
        return {"type": "single", "license": ""}

    license_expr = license_expr.strip()

    # Remove outer parentheses if they wrap the entire expression
    while license_expr.startswith("(") and license_expr.endswith(")"):
        # Check if these are the outermost matching parentheses
        depth = 0
        is_outer = True
        for i, char in enumerate(license_expr[1:-1], 1):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0 and i < len(license_expr) - 1:
                    is_outer = False
                    break
        if is_outer:
            license_expr = license_expr[1:-1].strip()
        else:
            break

    # Check for OR operator (lower precedence than AND)
    # Split by OR, respecting parentheses (case-insensitive)
    or_parts = _split_by_operator_case_insensitive(license_expr, "OR")
    if len(or_parts) > 1:
        # Recursively parse each OR part
        parsed_parts = [parse_license_expression(part) for part in or_parts]
        # Flatten if parts are already parsed
        licenses = []
        for part in parsed_parts:
            if part["type"] == "single":
                licenses.append(part["license"])
            elif part["type"] == "or":
                licenses.extend(part["licenses"])
            else:
                # Keep complex expressions as sub-structures
                licenses.append(part)
        return {"type": "or", "licenses": licenses}

    # Check for AND operator
    and_parts = _split_by_operator_case_insensitive(license_expr, "AND")
    if len(and_parts) > 1:
        # Recursively parse each AND part
        parsed_parts = [parse_license_expression(part) for part in and_parts]
        # Flatten if parts are already parsed
        licenses = []
        for part in parsed_parts:
            if part["type"] == "single":
                licenses.append(part["license"])
            elif part["type"] == "and":
                licenses.extend(part["licenses"])
            else:
                # Keep complex expressions as sub-structures
                licenses.append(part)
        return {"type": "and", "licenses": licenses}

    # Single license
    return {"type": "single", "license": license_expr}


def _split_by_operator(expr, operator):
    """
    Split expression by operator, respecting parentheses.

    Args:
        expr: License expression string
        operator: Operator to split by (e.g., " AND ", " OR ")

    Returns:
        list: Parts split by operator
    """
    parts = []
    current = []
    depth = 0
    i = 0

    while i < len(expr):
        char = expr[i]

        if char == "(":
            depth += 1
            current.append(char)
            i += 1
        elif char == ")":
            depth -= 1
            current.append(char)
            i += 1
        elif depth == 0 and expr[i:i+len(operator)] == operator:
            # Found operator at depth 0
            parts.append("".join(current).strip())
            current = []
            i += len(operator)
        else:
            current.append(char)
            i += 1

    # Add remaining part
    if current:
        parts.append("".join(current).strip())

    return parts if parts else [expr]


def _split_by_operator_case_insensitive(expr, operator):
    """
    Split expression by operator (case-insensitive), respecting parentheses.

    Args:
        expr: License expression string
        operator: Operator to split by (e.g., "AND", "OR") - will match any case

    Returns:
        list: Parts split by operator
    """
    parts = []
    current = []
    depth = 0
    i = 0

    # Create regex pattern for case-insensitive operator matching
    # Operator must be surrounded by spaces
    operator_lower = operator.lower()

    while i < len(expr):
        char = expr[i]

        if char == "(":
            depth += 1
            current.append(char)
            i += 1
        elif char == ")":
            depth -= 1
            current.append(char)
            i += 1
        elif depth == 0 and i > 0 and i < len(expr) - 1:
            # Check if we're at a potential operator position
            # Look for space + operator + space (case-insensitive)
            if expr[i-1:i] == " " or i == 1:
                # Check if the next few characters match the operator (case-insensitive)
                end_pos = i + len(operator)
                if end_pos < len(expr) and expr[i:end_pos].lower() == operator_lower:
                    # Check if followed by space or end of string
                    if end_pos < len(expr) and expr[end_pos] == " ":
                        # Found operator at depth 0
                        # Remove trailing space from current
                        current_str = "".join(current).rstrip()
                        parts.append(current_str)
                        current = []
                        i = end_pos + 1  # Skip operator and following space
                        continue

        current.append(char)
        i += 1

    # Add remaining part
    if current:
        parts.append("".join(current).strip())

    return parts if len(parts) > 1 else [expr]


def get_licenses_from_expression(license_expr):
    """
    Extract all unique license names from a license expression.

    Args:
        license_expr: SPDX license expression string

    Returns:
        list: List of individual license names
    """
    parsed = parse_license_expression(license_expr)
    licenses = set()

    def extract_licenses(node):
        if isinstance(node, dict):
            if node["type"] == "single":
                if node["license"]:
                    licenses.add(node["license"])
            elif node["type"] in ["and", "or"]:
                for lic in node["licenses"]:
                    if isinstance(lic, str):
                        licenses.add(lic)
                    else:
                        extract_licenses(lic)
        elif isinstance(node, str):
            licenses.add(node)

    extract_licenses(parsed)
    return list(licenses)


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
    # Check cache first
    if license_name in _license_text_cache:
        return _license_text_cache[license_name]

    # Handle special licenses that don't require license text
    if is_special_license(license_name):
        license_sources[license_name] = "Special license (no text required)"
        special_licenses_skipped.add(license_name)
        if license_name == "Public Domain":
            result = "This software is in the Public Domain and is not subject to copyright restrictions."
        elif license_name == "collection of licenses":
            result = "This component contains a collection of different licenses. Please refer to the original source for specific license terms."
        else:
            result = f"Special license type: {license_name}"
        _license_text_cache[license_name] = result
        return result

    url = get_license_url(license_name)
    if url:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                license_sources[license_name] = url
                _license_text_cache[license_name] = resp.text
                return resp.text
        except Exception:
            pass

    # Try local file
    local_filename = os.path.join(licenses_dir, sanitize_filename(license_name) + ".txt")
    if os.path.isfile(local_filename):
        try:
            with open(local_filename, "r", encoding="utf-8") as lf:
                result = lf.read()
                license_sources[license_name] = local_filename
                _license_text_cache[license_name] = result
                return result
        except Exception:
            pass

    # Handle LicenseRef-* as a workaround - try to use the referenced license
    if license_name.startswith("LicenseRef-"):
        referenced_license = license_name[len("LicenseRef-"):]
        # Try to get the referenced license text
        ref_url = get_license_url(referenced_license)
        if ref_url:
            try:
                resp = requests.get(ref_url, timeout=10)
                if resp.status_code == 200:
                    license_sources[license_name] = f"URL: {ref_url}"
                    result = f"[Using license text for '{referenced_license}' for LicenseRef]\n\n{resp.text}"
                    _license_text_cache[license_name] = result
                    return result
            except Exception:
                pass

        # Try local file for referenced license
        local_filename = os.path.join(licenses_dir, sanitize_filename(referenced_license) + ".txt")
        if os.path.isfile(local_filename):
            try:
                with open(local_filename, "r", encoding="utf-8") as lf:
                    license_text = lf.read()
                    license_sources[license_name] = f"File (via LicenseRef): {local_filename}"
                    result = f"[Using license text for '{referenced_license}' for LicenseRef]\n\n{license_text}"
                    _license_text_cache[license_name] = result
                    return result
            except Exception:
                pass

    failed_licenses.append(license_name)
    license_sources[license_name] = None
    _license_text_cache[license_name] = None
    return None


def download_license_expression_text(license_expr, license_sources, failed_licenses, licenses_dir, special_licenses_skipped):
    """
    Download license text for a license expression (handles AND/OR operators).

    For AND expressions: Include all required license texts.
    For OR expressions: Include first available license text from alternatives.

    Args:
        license_expr: SPDX license expression string
        license_sources: Dict to track license sources
        failed_licenses: List to track failed downloads
        licenses_dir: Directory containing local license files
        special_licenses_skipped: Set of special licenses

    Returns:
        str: Combined license text or error message
    """
    parsed = parse_license_expression(license_expr)

    if parsed["type"] == "single":
        return download_license_text(parsed["license"], license_sources, failed_licenses,
                                    licenses_dir, special_licenses_skipped)

    elif parsed["type"] == "and":
        # For AND: Include all license texts
        texts = []
        all_licenses = []

        for lic in parsed["licenses"]:
            if isinstance(lic, str):
                all_licenses.append(lic)
            elif isinstance(lic, dict):
                # Nested expression
                nested_text = download_license_expression_text(
                    _reconstruct_expression(lic),
                    license_sources, failed_licenses, licenses_dir, special_licenses_skipped
                )
                if nested_text is not None:
                    texts.append(nested_text)

        # Download all individual licenses
        for lic in all_licenses:
            text = download_license_text(lic, license_sources, failed_licenses,
                                        licenses_dir, special_licenses_skipped)
            if text is not None:
                texts.append(f"--- {lic} ---\n\n{text}")

        if not texts:
            return None

        return "\n\n" + "="*60 + "\n\n".join(texts)

    elif parsed["type"] == "or":
        # For OR: Try to get first available license text
        for lic in parsed["licenses"]:
            if isinstance(lic, str):
                # Try to download this license
                text = download_license_text(lic, license_sources, failed_licenses,
                                            licenses_dir, special_licenses_skipped)
                # Check if download was successful
                if text is not None:
                    # Successfully got license text, return it
                    return f"--- {lic} (chosen from OR alternatives) ---\n\n{text}"
            elif isinstance(lic, dict):
                # Nested expression
                nested_text = download_license_expression_text(
                    _reconstruct_expression(lic),
                    license_sources, failed_licenses, licenses_dir, special_licenses_skipped
                )
                if nested_text is not None:
                    return nested_text

        # None of the OR alternatives were found
        return None

    return None


def _reconstruct_expression(parsed):
    """Reconstruct license expression string from parsed structure."""
    if parsed["type"] == "single":
        return parsed["license"]
    elif parsed["type"] == "and":
        parts = [_reconstruct_expression(lic) if isinstance(lic, dict) else lic
                for lic in parsed["licenses"]]
        return " AND ".join(parts)
    elif parsed["type"] == "or":
        parts = [_reconstruct_expression(lic) if isinstance(lic, dict) else lic
                for lic in parsed["licenses"]]
        return " OR ".join(parts)
    return ""


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
                # Parse license expression to get all individual licenses
                individual_licenses = get_licenses_from_expression(license_)
                for lic in individual_licenses:
                    if lic:
                        licenses.add(lic)

                # Store the original expression for this component
                license_to_components[license_].append(component)

    # Sort licenses and components
    licenses_sorted = sorted(licenses, key=lambda x: x.lower())

    # Group components by their license expression
    license_expr_to_components = defaultdict(list)
    for component, license_expr in components:
        if license_expr:
            license_expr_to_components[license_expr].append(component)

    # Sort license expressions and their components
    for license_expr in license_expr_to_components:
        license_expr_to_components[license_expr] = sorted(
            set(license_expr_to_components[license_expr]),
            key=lambda x: x.lower()
        )

    # Read preamble
    preamble = ""
    if os.path.isfile(preamble_file):
        with open(preamble_file, "r", encoding="utf-8") as pf:
            preamble = pf.read().rstrip() + "\n"

    # Generate output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(preamble)

        # Sort license expressions for consistent output
        sorted_license_exprs = sorted(license_expr_to_components.keys(), key=lambda x: x.lower())

        entry_num = 1
        for license_expr in sorted_license_exprs:
            # Download license text for the expression
            license_text = download_license_expression_text(
                license_expr, license_sources, failed_licenses, licenses_dir, special_licenses_skipped
            )

            # Only write entry if license text was found
            if license_text is not None:
                f.write("\n\n")
                f.write("-------------------------------------------------------------\n")
                f.write(f"{entry_num}. Software released under the license {license_expr}:\n")
                for comp in license_expr_to_components[license_expr]:
                    f.write(f"    {comp}\n")
                f.write("\n")
                f.write(license_text.strip() + "\n")
                entry_num += 1

    # Print summary
    print(f"Processed {len(components)} total components")
    print(f"Found {len(licenses_sorted)} unique individual licenses")
    print(f"Found {len(sorted_license_exprs)} unique license expressions")

    print("\nUnique individual licenses used (with source):")
    for lic in licenses_sorted:
        src = license_sources.get(lic)
        if src is None:
            src_str = "None"
        elif isinstance(src, str) and src.startswith("http"):
            src_str = f"URL: {src}"
        elif isinstance(src, str):
            src_str = f"File: {src}"
        else:
            src_str = str(src)
        print(f" - {lic} [{src_str}]")

    if special_licenses_skipped:
        print("\nSpecial licenses (no license text required):")
        for lic in sorted(special_licenses_skipped):
            print(f" - {lic}")
        print("\nNote: These special license types are included in the output with explanatory text only.")

    if failed_licenses:
        # Remove duplicates and sort
        unique_failed = sorted(set(failed_licenses))
        print("\nFailed to obtain license text for the following licenses:")
        for lic in unique_failed:
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
