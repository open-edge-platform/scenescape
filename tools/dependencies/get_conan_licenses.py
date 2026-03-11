# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""
Resolve Conan package licenses from *-conan-deps.txt files using `conan inspect`.

Prerequisite: `make list-dependencies` must have been run so that
*-conan-deps.txt files exist in the build directory, and `conan` must be
available on PATH (install via: pipx install conan).

Usage:
  # Write per-image *-conan-licenses.csv to the same build directory
  python3 tools/dependencies/get_conan_licenses.py build/

  # Also write a consolidated CSV
  python3 tools/dependencies/get_conan_licenses.py build/ -o build/all-conan-licenses.csv

The script:
  - Scans build_dir for *-conan-deps.txt files
  - Parses "name version" lines (one per package)
  - Resolves license via local Conan cache (fast) when available, or falls back
    to `conan graph info --requires=name/version` which queries configured remotes
    (e.g. conancenter) — useful when packages were built inside Docker and are not
    in the host cache
  - Caches results in-memory to avoid duplicate calls across images
  - Writes <build_dir>/<image>-conan-licenses.csv (Name,Version,License)
  - Optionally writes a combined Image,Component,License CSV for review

Also importable as a library: use load_conan_licenses(build_dir) to get a
(image, component) -> license mapping for use in update_dependencies.py.
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CONAN_DEPS_SUFFIX = "-conan-deps.txt"
CONAN_LICENSES_SUFFIX = "-conan-licenses.csv"


def _check_conan() -> str:
    """Return the path to the conan executable, or exit with a clear error."""
    conan = shutil.which("conan")
    if not conan:
        print(
            "Error: 'conan' not found on PATH.\n"
            "Install it with:  pipx install conan\n"
            "Then ensure it is on PATH:  pipx ensurepath",
            file=sys.stderr,
        )
        sys.exit(1)
    return conan


def inspect_conan(name: str, version: str, cache: Dict[str, str], conan: str) -> str:
    """Return the license string for *name*/*version* via `conan inspect`.

    Results are stored in *cache* keyed by ``"name/version"``.
    Returns an empty string when the license cannot be determined.
    """
    cache_key = f"{name}/{version}"
    if cache_key in cache:
        return cache[cache_key]

    license_val = ""

    # --- Strategy 1: local Conan cache (fast, no network needed) ---
    try:
        path_result = subprocess.run(
            [conan, "cache", "path", cache_key],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if path_result.returncode == 0:
            recipe_path = path_result.stdout.strip()
            result = subprocess.run(
                [conan, "inspect", recipe_path, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                raw = data.get("license", "")
                if isinstance(raw, list):
                    license_val = ", ".join(str(x) for x in raw if x)
                elif isinstance(raw, str):
                    license_val = raw.strip()
    except Exception:
        pass  # fall through to strategy 2

    # --- Strategy 2: conan graph info (queries remotes, no local cache needed) ---
    if not license_val:
        try:
            result = subprocess.run(
                [conan, "graph", "info", f"--requires={cache_key}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr like 2>&1
                text=True,
                timeout=120,
            )
            # Package data header at column 0: "name/version#<hash>:"
            # Progress messages also start with "name/version:" but lack the "#"
            # License in indented line: "  license: Apache-2.0"
            in_block = False
            for line in result.stdout.splitlines():
                if re.match(rf"^{re.escape(name)}/{re.escape(version)}#", line):
                    in_block = True
                    continue
                if in_block:
                    m = re.match(r"^\s+license:\s+(.+)$", line)
                    if m:
                        val = m.group(1).strip()
                        if val.lower() != "none":
                            license_val = val
                        break
                    # Non-indented line starts the next package block
                    if line and not line[0].isspace():
                        break
        except subprocess.TimeoutExpired:
            print(f"  Warning: conan graph info timed out for {cache_key}", file=sys.stderr)
        except Exception as exc:
            print(f"  Warning: conan graph info error for {cache_key}: {exc}", file=sys.stderr)

    cache[cache_key] = license_val
    return license_val


def parse_conan_deps_line(line: str) -> Optional[Tuple[str, str]]:
    """Parse one line from a *-conan-deps.txt file.

    Expected format: ``name version``
    Returns (name, version) or None for blank/comment lines.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0], ""


def process_image(
    conan_deps_file: Path, cache: Dict[str, str], conan: str
) -> List[Tuple[str, str, str]]:
    """Process one *-conan-deps.txt file and return (name, version, license) rows."""
    rows: List[Tuple[str, str, str]] = []
    try:
        lines = conan_deps_file.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        print(f"Warning: could not read {conan_deps_file}: {exc}", file=sys.stderr)
        return rows

    for line in lines:
        parsed = parse_conan_deps_line(line)
        if parsed is None:
            continue
        name, version = parsed
        license_val = inspect_conan(name, version, cache, conan)
        rows.append((name, version, license_val))

    return rows


def write_image_csv(rows: List[Tuple[str, str, str]], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Name", "Version", "License"])
        for row in rows:
            writer.writerow(row)


def load_conan_licenses(build_dir: str) -> Dict[Tuple[str, str], str]:
    """Load conan-licenses data from per-image *-conan-licenses.csv files.

    Returns a dict mapping ``(image, component)`` → ``license`` where
    *component* uses the ``name/version`` format (same as generate_dependencies.py).
    Several key variants are stored for flexible look-up:

    * ``(image, "name/version")``  – versioned, original casing
    * ``(image, "name")``          – name-only

    Non-fatal: if a file cannot be read a warning is printed and skipped.
    """
    build_path = Path(build_dir)
    if not build_path.exists():
        print(
            f"Warning: conan-licenses directory '{build_dir}' not found, skipping",
            file=sys.stderr,
        )
        return {}

    csv_files = sorted(build_path.glob(f"*{CONAN_LICENSES_SUFFIX}"))
    if not csv_files:
        print(
            f"Warning: no *{CONAN_LICENSES_SUFFIX} files found in '{build_dir}', skipping",
            file=sys.stderr,
        )
        return {}

    print(f"Loading conan-licenses data from {len(csv_files)} file(s)...")
    mapping: Dict[Tuple[str, str], str] = {}

    for csv_file in csv_files:
        image = csv_file.name[: -len(CONAN_LICENSES_SUFFIX)]
        try:
            with open(csv_file, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    name = row.get("Name", "").strip()
                    version = row.get("Version", "").strip()
                    license_val = row.get("License", "").strip()
                    if not name or not license_val:
                        continue
                    versioned = f"{name}/{version}" if version else name
                    for key in [(image, versioned), (image, name)]:
                        mapping.setdefault(key, license_val)
        except Exception as exc:
            print(f"Warning: could not read {csv_file}: {exc}", file=sys.stderr)

    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve Conan package licenses from *-conan-deps.txt files "
            "using `conan inspect`. Requires conan on PATH."
        )
    )
    parser.add_argument(
        "build_dir",
        help="Build directory containing *-conan-deps.txt files",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "Optional: write a consolidated Image,Component,License CSV "
            "(e.g. build/all-conan-licenses.csv)"
        ),
    )
    args = parser.parse_args()

    conan = _check_conan()

    build_path = Path(args.build_dir)
    if not build_path.exists():
        print(f"Error: build directory '{args.build_dir}' not found", file=sys.stderr)
        return 1

    dep_files = sorted(build_path.glob(f"*{CONAN_DEPS_SUFFIX}"))
    if not dep_files:
        print(f"No *{CONAN_DEPS_SUFFIX} files found in '{args.build_dir}'")
        return 1

    print(f"Processing {len(dep_files)} conan-deps file(s)...")

    cache: Dict[str, str] = {}
    consolidated: List[Tuple[str, str, str, str]] = []  # (image, name, version, license)

    for dep_file in dep_files:
        image = dep_file.name[: -len(CONAN_DEPS_SUFFIX)]
        print(f"  [{image}] inspecting Conan packages...", end="", flush=True)

        rows = process_image(dep_file, cache, conan)

        out_file = build_path / f"{image}{CONAN_LICENSES_SUFFIX}"
        write_image_csv(rows, out_file)
        print(f" {len(rows)} packages -> {out_file.name}")

        for name, version, lic in rows:
            component = f"{name}/{version}" if version else name
            consolidated.append((image, component, lic))

    print(f"\nTotal unique Conan inspections: {len(cache)}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Image", "Component", "License"])
            for row in consolidated:
                writer.writerow(row)
        print(f"Consolidated CSV written to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
