#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate Dockerfile artifacts zip and image summary table.

Produces:
  - Dockerfiles-<version-slug>.zip   Dockerfiles and requirements files, plus a
                                     gpllist of copyleft-licensed distributed packages
  - Markdown summary table of all images (--summary-file or stdout)

Usage (from repo root):
    python3 tools/dependencies/generate_dockerfile_artifacts.py [OPTIONS]

Options:
    --repo-root PATH     Repository root directory (default: cwd)
    --output-dir PATH    Output directory (default: <repo-root>/build/)
    --deps PATH          Dependencies CSV file (auto-detected from release-data/)
    --image-list PATH    Images CSV file (auto-detected from release-data/)
    --zip-name NAME      Zip filename (default: Dockerfiles-<version-slug>.zip)
    --summary-file PATH  Write Markdown summary to this file (default: stdout)

The zip layout mirrors the 2025.2 example:
    Dockerfiles-<slug>.zip/
        gpllist-<slug>
        sources-<slug>.Dockerfile
        Dockerfile-common
        Dockerfile-tests
        manager/
            Dockerfile
            requirements-runtime.txt
        controller/
            Dockerfile
            requirements-runtime.txt
        camcalibration/
            Dockerfile
            requirements-runtime.txt
        ...

Image CSV columns expected:
    Image, Dockerfile Path, Dockerfile Name, Report Dependencies, Published, Comment

Dependencies CSV columns expected:
    Image, Component, Origin, License, Distributed by you?, Comments
"""

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path

# Licenses that require source distribution under open-source compliance policies
COPYLEFT_RE = re.compile(
    r"\b(A?GPL|LGPL|MPL|EPL|EUPL|CDDL|SSPL|BUSL|APSL)\b",
    re.IGNORECASE,
)

# Dockerfile Names that are placed at the top level of the zip without a subfolder
TOP_LEVEL_NAMES = {"Dockerfile-tests"}


def get_version_slug(version_str: str) -> str:
    """Convert a version string to a short slug.

    Examples:
        '2025.2.0'     -> '2025-2'
        '2026.0.0-rc1' -> '2026-0'
    """
    parts = version_str.strip().split(".")
    major = parts[0]
    minor = parts[1].split("-")[0] if len(parts) > 1 else "0"
    return f"{major}-{minor}"


def find_latest_csv(data_dir: Path, pattern: str) -> Path:
    matches = sorted(data_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No file matching '{pattern}' found in {data_dir}"
        )
    return matches[-1]


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def generate_gpllist(deps: list[dict]) -> list[str]:
    """Collect unique component identifiers that have copyleft licenses and
    are distributed (Distributed by you? == 'Y')."""
    seen: set[str] = set()
    for row in deps:
        distributed = row.get("Distributed by you?", "").strip().upper()
        license_val = row.get("License", "")
        if distributed == "Y" and COPYLEFT_RE.search(license_val):
            seen.add(row["Component"].strip())
    return sorted(seen)


def zip_subfolder_for(dockerfile_name: str) -> str | None:
    """Return the subfolder name inside the zip for this Dockerfile Name,
    or None if it should be placed at the top level."""
    if dockerfile_name in TOP_LEVEL_NAMES:
        return None
    if dockerfile_name == "sources.Dockerfile":
        return None  # top-level, but renamed
    if dockerfile_name.startswith("Dockerfile-"):
        return dockerfile_name[len("Dockerfile-"):]
    return None


def build_zip(
    images: list[dict],
    repo_root: Path,
    version_slug: str,
    gpllist: list[str],
    output_zip: Path,
) -> list[str]:
    """Create the Dockerfiles zip. Returns list of archive paths added."""
    entries: list[str] = []

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:

        # gpllist — always included
        gpllist_name = f"gpllist-{version_slug}"
        zf.writestr(gpllist_name, "\n".join(gpllist) + "\n")
        entries.append(gpllist_name)

        for row in images:
            image_name = row.get("Image", "").strip()
            dockerfile_path_rel = row.get("Dockerfile Path", "").strip()
            dockerfile_name = row.get("Dockerfile Name", "").strip()
            report_deps = row.get("Report Dependencies", "").strip().upper()

            if not dockerfile_path_rel or not dockerfile_name:
                print(
                    f"Warning: skipping row with missing path/name for image '{image_name}'",
                    file=sys.stderr,
                )
                continue

            src = repo_root / dockerfile_path_rel
            if not src.exists():
                print(
                    f"Warning: Dockerfile not found: {src}",
                    file=sys.stderr,
                )
                continue

            # sources.Dockerfile — renamed at top level
            if dockerfile_name == "sources.Dockerfile":
                archive_path = f"sources-{version_slug}.Dockerfile"
                zf.write(src, archive_path)
                entries.append(archive_path)
                continue

            subfolder = zip_subfolder_for(dockerfile_name)

            dockerfile_dir = (repo_root / dockerfile_path_rel).parent

            if subfolder is None:
                # Top-level (Dockerfile-common, Dockerfile-tests)
                zf.write(src, dockerfile_name)
                entries.append(dockerfile_name)
                # Add any requirements files, prefixed with the Dockerfile suffix
                # e.g. "Dockerfile-common" → prefix "common" → "requirements-common.txt"
                prefix = dockerfile_name.split("-", 1)[1] if "-" in dockerfile_name else dockerfile_name
                for req in sorted(dockerfile_dir.glob("requirements*.txt")):
                    req_archive = f"requirements-{prefix}{req.name[len('requirements'):]}"
                    zf.write(req, req_archive)
                    entries.append(req_archive)
            else:
                # Place inside service subfolder as "Dockerfile"
                archive_path = f"{subfolder}/Dockerfile"
                zf.write(src, archive_path)
                entries.append(archive_path)

                # Include requirements*.txt files from the Dockerfile's directory
                for req in sorted(dockerfile_dir.glob("requirements*.txt")):
                    req_archive = f"{subfolder}/{req.name}"
                    zf.write(req, req_archive)
                    entries.append(req_archive)

    return entries


def generate_summary_table(images: list[dict]) -> str:
    """Render the image list as a Markdown table."""
    cols = [
        "Image",
        "Dockerfile Path",
        "Dockerfile Name",
        "Report Dependencies",
        "Published",
        "Comment",
    ]
    widths = {c: len(c) for c in cols}
    for row in images:
        for c in cols:
            widths[c] = max(widths[c], len(row.get(c, "")))

    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[cols[i]]) for i, c in enumerate(cells)) + " |"

    separator = "| " + " | ".join("-" * widths[c] for c in cols) + " |"

    lines = [fmt_row(cols), separator]
    for row in images:
        lines.append(fmt_row([row.get(c, "") for c in cols]))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Dockerfile artifacts zip and image summary table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: cwd)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <repo-root>/build/)",
    )
    parser.add_argument(
        "--deps",
        type=Path,
        default=None,
        help="Dependencies CSV (auto-detected from release-data/ if omitted)",
    )
    parser.add_argument(
        "--image-list",
        type=Path,
        default=None,
        help="Images CSV (auto-detected from release-data/ if omitted)",
    )
    parser.add_argument(
        "--zip-name",
        type=str,
        default=None,
        help="Zip filename (default: Dockerfiles-<version-slug>.zip)",
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Write Markdown summary table to this file (default: stdout)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_dir = (args.output_dir or repo_root / "build").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Version
    version_file = repo_root / "version.txt"
    if not version_file.exists():
        sys.exit(f"Error: version.txt not found at {version_file}")
    version_str = version_file.read_text(encoding="utf-8").strip()
    version_slug = get_version_slug(version_str)
    print(f"Version : {version_str}  (slug: {version_slug})")

    # Locate CSVs
    release_data_dir = repo_root / "tools" / "dependencies" / "release-data"
    image_list_path = args.image_list or find_latest_csv(release_data_dir, "*-Images.csv")
    deps_path = args.deps or find_latest_csv(release_data_dir, "*-Dependencies.csv")
    print(f"Images  : {image_list_path}")
    print(f"Deps    : {deps_path}")

    images = load_csv(image_list_path)
    deps = load_csv(deps_path)

    # gpllist
    gpllist = generate_gpllist(deps)
    print(f"gpllist : {len(gpllist)} copyleft-licensed distributed packages")

    # Build zip
    zip_name = args.zip_name or f"Dockerfiles-{version_slug}.zip"
    output_zip = output_dir / zip_name
    entries = build_zip(images, repo_root, version_slug, gpllist, output_zip)
    print(f"\nCreated : {output_zip}")
    for entry in entries:
        print(f"  {entry}")

    # Summary table
    summary = generate_summary_table(images)
    if args.summary_file:
        args.summary_file.parent.mkdir(parents=True, exist_ok=True)
        args.summary_file.write_text(summary + "\n", encoding="utf-8")
        print(f"\nSummary : {args.summary_file}")
    else:
        print("\n## Image Summary\n")
        print(summary)


if __name__ == "__main__":
    main()
