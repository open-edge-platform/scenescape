# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""
Convert SPDX JSON SBOMs produced by `make generate-sboms` to CSV.

Prerequisite: `make generate-sboms` must have been run so that
*-sbom.spdx.json files exist in build/sboms/.

Usage:
  # Write per-image *-sbom.csv files to the same directory
  python3 tools/dependencies/spdx_json_to_csv.py build/sboms/

  # Also write a consolidated CSV
  python3 tools/dependencies/spdx_json_to_csv.py build/sboms/ -o build/all-sbom.csv

The script:
  - Scans sboms_dir for *-sbom.spdx.json files
  - Derives the image name from the filename (e.g. scenescape-manager-sbom.spdx.json -> scenescape-manager)
  - Maps SPDX package origin from SPDXRef prefix (deb->Ubuntu, python->pypi, npm->npm)
  - Writes <sboms_dir>/<image>-sbom.csv (Image,Component,Origin,License)
  - Optionally writes a combined CSV for review
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Tuple

SBOM_SUFFIX = "-sbom.spdx.json"
CSV_SUFFIX = "-sbom.csv"
COLUMN_NAMES = ["Image", "Component", "Origin", "License"]


def _normalize_license(lic) -> str:
    if not lic or str(lic).strip().upper() in ("NOASSERTION", "NONE", ""):
        return "NOASSERTION"
    return str(lic).strip()


def _origin_and_component(spdxid: str, name: str, version: str) -> Tuple[str, str]:
    """Derive (origin, component) from SPDXRef prefix and package fields."""
    if spdxid.startswith("SPDXRef-Package-deb"):
        return "Ubuntu", f"{name}:{version}" if version else name
    if spdxid.startswith("SPDXRef-Package-python"):
        return "pypi", f"{name}=={version}" if version else name
    if spdxid.startswith("SPDXRef-Package-npm"):
        return "npm", f"{name}@{version}" if version else name
    return "UNKNOWN", f"{name}:{version}" if version else name


def parse_sbom(json_path: Path, image_name: str) -> List[Tuple[str, str, str, str]]:
    """Parse one *-sbom.spdx.json and return (image, component, origin, license) rows."""
    with open(json_path, encoding="utf-8") as fh:
        doc = json.load(fh)

    # Support both bare SPDX doc and in-toto attestation wrapper
    predicate = doc.get("predicate", doc)
    packages = predicate.get("packages", [])

    rows = []
    for pkg in packages:
        name = pkg.get("name", "UNKNOWN")
        version = pkg.get("versionInfo", "")
        spdxid = pkg.get("SPDXID", "")
        origin, component = _origin_and_component(spdxid, name, version)
        license_val = _normalize_license(pkg.get("licenseDeclared"))
        rows.append((image_name, component, origin, license_val))
    return rows


def write_csv(rows: List[Tuple[str, str, str, str]], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMN_NAMES)
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert SPDX JSON SBOMs to CSV. Scans a directory for *-sbom.spdx.json files."
    )
    parser.add_argument(
        "sboms_dir",
        help="Directory containing *-sbom.spdx.json files (e.g. build/sboms/)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Optional: write a consolidated Image,Component,Origin,License CSV",
    )
    args = parser.parse_args()

    sboms_path = Path(args.sboms_dir)
    if not sboms_path.exists():
        print(f"Error: directory '{args.sboms_dir}' not found", file=sys.stderr)
        return 1

    sbom_files = sorted(sboms_path.glob(f"*{SBOM_SUFFIX}"))
    if not sbom_files:
        print(f"No *{SBOM_SUFFIX} files found in '{args.sboms_dir}'", file=sys.stderr)
        return 1

    print(f"Processing {len(sbom_files)} SBOM file(s)...")

    consolidated: List[Tuple[str, str, str, str]] = []

    for sbom_file in sbom_files:
        image = sbom_file.name[: -len(SBOM_SUFFIX)]
        try:
            rows = parse_sbom(sbom_file, image)
        except Exception as exc:
            print(f"  Warning: could not parse {sbom_file.name}: {exc}", file=sys.stderr)
            continue

        out_file = sboms_path / f"{image}{CSV_SUFFIX}"
        write_csv(rows, out_file)
        print(f"  [{image}] {len(rows)} packages -> {out_file.name}")
        consolidated.extend(rows)

    print(f"\nTotal packages across all images: {len(consolidated)}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_csv(consolidated, out_path)
        print(f"Consolidated CSV written to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
