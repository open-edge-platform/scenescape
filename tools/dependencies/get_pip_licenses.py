# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""
Resolve PyPI package licenses from *-pip-deps.txt files using the PyPI JSON API.

Prerequisite: `make list-dependencies` must have been run so that
*-pip-deps.txt files exist in the build directory.

Usage:
  # Write per-image *-pip-licenses.csv to the same build directory
  python3 tools/dependencies/get_pip_licenses.py build/

  # Also write a consolidated CSV
  python3 tools/dependencies/get_pip_licenses.py build/ -o build/all-pip-licenses.csv

The script:
  - Scans build_dir for *-pip-deps.txt files
  - Parses pip-freeze format lines (skips local/VCS/editable installs)
  - Queries https://pypi.org/pypi/{name}/{version}/json for license metadata
  - Falls back to Trove classifiers when the License field is empty
  - Caches results in-memory to avoid duplicate API calls across images
  - Writes <build_dir>/<image>-pip-licenses.csv (Name,Version,License)
  - Optionally writes a combined Image,Component,License CSV for review

Also importable as a library: use load_pip_licenses(build_dir) to get a
(image, component) -> license mapping for use in update_dependencies.py.
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PIP_DEPS_SUFFIX = "-pip-deps.txt"
PIP_LICENSES_SUFFIX = "-pip-licenses.csv"
PYPI_API = "https://pypi.org/pypi/{name}/{version}/json"
PYPI_LATEST_API = "https://pypi.org/pypi/{name}/json"
REQUEST_DELAY = 0.05  # seconds between API calls (be polite)
REQUEST_TIMEOUT = 30


def _normalize_name(name: str) -> str:
  """Lower-case and normalise package name (PEP 503 style)."""
  return name.lower().replace("-", "_").replace(".", "_")


def load_pip_licenses(build_dir: str) -> Dict[Tuple[str, str], str]:
  """Load pip-licenses data from per-image *-pip-licenses.csv files in *build_dir*.

  Returns a dict mapping ``(image, component)`` → ``license`` where
  *component* uses the ``Name==Version`` format (same as used throughout
  ``update_dependencies.py``).  Several key variants are stored so that
  look-ups succeed regardless of exact capitalisation or whether a version
  was specified:

  * ``(image, "Name==Version")``  – exact, original casing
  * ``(image, "norm==Version")``  – normalised name, original version
  * ``(image, "Name")``       – name-only, original casing
  * ``(image, "norm")``       – name-only, normalised

  Non-fatal: if a file cannot be read a warning is printed and skipped.
  """
  build_path = Path(build_dir)
  if not build_path.exists():
    print(f"Warning: pip-licenses directory '{build_dir}' not found, skipping pip-licenses resolution")
    return {}

  csv_files = sorted(build_path.glob(f"*{PIP_LICENSES_SUFFIX}"))
  if not csv_files:
    print(f"Warning: no *{PIP_LICENSES_SUFFIX} files found in '{build_dir}', skipping pip-licenses resolution")
    return {}

  print(f"Loading pip-licenses data from {len(csv_files)} files...")
  mapping: Dict[Tuple[str, str], str] = {}

  for csv_file in csv_files:
    image = csv_file.name[: -len(PIP_LICENSES_SUFFIX)]
    try:
      with open(csv_file, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
          name = row.get("Name", "").strip()
          version = row.get("Version", "").strip()
          license_val = row.get("License", "").strip()

          if not name or not license_val:
            continue

          norm = _normalize_name(name)
          versioned = f"{name}=={version}" if version else name
          versioned_norm = f"{norm}=={version}" if version else norm

          for key in [
            (image, versioned),
            (image, versioned_norm),
            (image, name),
            (image, norm),
          ]:
            mapping.setdefault(key, license_val)

    except Exception as exc:
      print(f"Warning: could not read {csv_file}: {exc}")

  return mapping
PYPI_API = "https://pypi.org/pypi/{name}/{version}/json"
PYPI_LATEST_API = "https://pypi.org/pypi/{name}/json"
REQUEST_DELAY = 0.05  # seconds between API calls (be polite)
REQUEST_TIMEOUT = 30
RETRY_COUNT = 5
RETRY_BACKOFF = 2.0  # seconds; doubles on each retry


def parse_pip_deps_line(line: str) -> Optional[Tuple[str, str]]:
  """Parse one line from a pip freeze output file.

  Returns (name, version) or None if the line should be skipped.
  Skips:
    - empty lines / comments
    - local wheel installs:  Name @ file://...
    - VCS installs:      Name @ https://...
    - editable installs:   -e git+...
  """
  line = line.strip()
  if not line or line.startswith("#"):
    return None
  if line.startswith("-e "):
    return None
  if " @ " in line:
    return None
  if "==" in line:
    name, version = line.split("==", 1)
    return name.strip(), version.strip()
  # Package listed without a version (e.g. compiled into the image)
  return line.strip(), ""


def query_pypi(name: str, version: str, cache: Dict[str, str]) -> str:
  """Return license string for *name*==*version* from the PyPI JSON API.

  Results are stored in *cache* keyed by ``"name==version"`` (lower-cased).
  Returns an empty string when the license cannot be determined.
  """
  cache_key = f"{name.lower()}=={version}"
  if cache_key in cache:
    return cache[cache_key]

  # Strip local version suffix (e.g. "2.10.0+cpu" → "2.10.0"); PyPI only
  # stores the public version and will 404 on local identifiers.
  pypi_version = version.split("+")[0] if version else version
  url = PYPI_API.format(name=name, version=pypi_version) if pypi_version else PYPI_LATEST_API.format(name=name)
  license_val = ""
  delay = RETRY_BACKOFF
  for attempt in range(1, RETRY_COUNT + 1):
    try:
      req = urllib.request.Request(
        url, headers={"User-Agent": "scenescape-dep-tool/1.0 (license-lookup)"}
      )
      with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read())

      info = data.get("info", {})

      # 1. SPDX expression (Python 3.12+ packaging metadata – concise)
      spdx = (info.get("license_expression") or "").strip()
      if spdx and spdx.upper() not in ("UNKNOWN", "NOASSERTION"):
        license_val = spdx

      # 2. license field – only when it looks like a name, not full text
      if not license_val:
        raw = (info.get("license") or "").strip()
        if raw and "\n" not in raw and len(raw) <= 80 and raw.upper() not in ("UNKNOWN", "NOASSERTION", "OTHER"):
          license_val = raw

      # 3. Trove classifiers (most specific wins)
      if not license_val:
        for cls in info.get("classifiers", []):
          if cls.startswith("License ::"):
            license_val = cls.split(" :: ")[-1].strip()
            break

      time.sleep(REQUEST_DELAY)
      break  # success – exit retry loop

    except urllib.error.HTTPError as exc:
      if exc.code == 404:
        break  # not on PyPI (private / local package)
      print(f"  Warning: HTTP {exc.code} for {name}=={version}", file=sys.stderr)
      break
    except urllib.error.URLError as exc:
      reason = str(exc.reason) if exc.reason else str(exc)
      retriable = "timed out" in reason.lower() or "connection reset" in reason.lower() or "104" in reason
      if retriable:
        if attempt < RETRY_COUNT:
          print(f"  Warning: {reason.strip()} for {name}=={version} (attempt {attempt}/{RETRY_COUNT}), retrying in {delay:.0f}s...", file=sys.stderr)
          time.sleep(delay)
          delay *= 2
          continue
        print(f"  Warning: could not fetch {name}=={version} after {RETRY_COUNT} attempts: {reason.strip()}", file=sys.stderr)
      else:
        print(f"  Warning: could not fetch {name}=={version}: {exc}", file=sys.stderr)
      break
    except Exception as exc:
      print(f"  Warning: could not fetch {name}=={version}: {exc}", file=sys.stderr)
      break

  cache[cache_key] = license_val
  return license_val


def process_image(pip_deps_file: Path, cache: Dict[str, str]) -> List[Tuple[str, str, str]]:
  """Process one *-pip-deps.txt file and return (name, version, license) rows."""
  rows: List[Tuple[str, str, str]] = []
  try:
    lines = pip_deps_file.read_text(encoding="utf-8").splitlines()
  except Exception as exc:
    print(f"Warning: could not read {pip_deps_file}: {exc}", file=sys.stderr)
    return rows

  for line in lines:
    parsed = parse_pip_deps_line(line)
    if parsed is None:
      continue
    name, version = parsed
    license_val = query_pypi(name, version, cache)
    rows.append((name, version, license_val))

  return rows


def write_image_csv(rows: List[Tuple[str, str, str]], output_path: Path) -> None:
  with open(output_path, "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["Name", "Version", "License"])
    for row in rows:
      writer.writerow(row)


def main() -> int:
  parser = argparse.ArgumentParser(
    description=(
      "Resolve PyPI package licenses from *-pip-deps.txt files "
      "using the PyPI JSON API. No Docker or package installation required."
    )
  )
  parser.add_argument(
    "build_dir",
    help="Build directory containing *-pip-deps.txt files",
  )
  parser.add_argument(
    "-o",
    "--output",
    default=None,
    help=(
      "Optional: write a consolidated Image,Component,License CSV "
      "(e.g. build/all-pip-licenses.csv)"
    ),
  )
  args = parser.parse_args()

  build_path = Path(args.build_dir)
  if not build_path.exists():
    print(f"Error: build directory '{args.build_dir}' not found")
    return 1

  dep_files = sorted(build_path.glob(f"*{PIP_DEPS_SUFFIX}"))
  if not dep_files:
    print(f"No *{PIP_DEPS_SUFFIX} files found in '{args.build_dir}'")
    return 1

  print(f"Processing {len(dep_files)} pip-deps file(s)...")

  cache: Dict[str, str] = {}
  consolidated: List[Tuple[str, str, str, str]] = []  # (image, name, version, license)

  for dep_file in dep_files:
    image = dep_file.name[: -len(PIP_DEPS_SUFFIX)]
    print(f"  [{image}] querying PyPI licenses...", end="", flush=True)

    rows = process_image(dep_file, cache)

    out_file = build_path / f"{image}{PIP_LICENSES_SUFFIX}"
    write_image_csv(rows, out_file)
    print(f" {len(rows)} packages -> {out_file.name}")

    for name, version, lic in rows:
      component = f"{name}=={version}" if version else name
      consolidated.append((image, component, lic))

  print(f"\nTotal unique PyPI lookups: {len(cache)}")

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
