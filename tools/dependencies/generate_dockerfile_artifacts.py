#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2025 - 2026 Intel Corporation
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

# Both old ("Distributed by you?") and new ("Distributed by you") column names
_DISTRIBUTED_COLS = ("Distributed by you?", "Distributed by you")

# Dockerfile Names that are placed at the top level of the zip without a subfolder
TOP_LEVEL_NAMES = {"Dockerfile-tests"}

# ---------------------------------------------------------------------------
# Sources Dockerfile generation
# ---------------------------------------------------------------------------

# Ordered list of (binary-package-name-prefix, debian-source-package-name).
# Longer/more-specific prefixes must come before shorter ones.
DEB_BINARY_TO_SOURCE: list[tuple[str, str]] = [
    ("libglib2.0",          "glib2.0"),
    ("libpython3.11",       "python3.11"),
    ("perl-modules",        "perl"),
    ("libheif-plugin",      "libheif"),
    ("libgeos-c",           "geos"),
    ("libgeos",             "geos"),
    ("libgdbm",             "gdbm"),
    ("libgfortran",         "gcc-12"),
    ("libgomp",             "gcc-12"),
    ("libquadmath",         "gcc-12"),
    ("libgcc-s",            "gcc-14"),
    ("libstdc++",           "gcc-14"),
    ("libc6",               "glibc"),
    ("libc-",               "glibc"),
    ("libgcc1",             "gcc-12"),
    ("libgdal",             "gdal"),
    ("gdal",                "gdal"),
    ("libgdcm",             "gdcm"),
    ("libarmadillo",        "armadillo"),
    ("libcfitsio",          "cfitsio"),
    ("libde265",            "libde265"),
    ("libelf",              "elfutils"),
    ("libfuse",             "fuse"),
    ("libfyba",             "fyba"),
    ("libgudev",            "libgudev"),
    ("libhdf4",             "libhdf4"),
    ("libhdf5",             "hdf5"),
    ("libheif",             "libheif"),
    ("libicu",              "icu"),
    ("libinput",            "libinput"),
    ("libjbig",             "jbigkit"),
    ("libjson-c",           "json-c"),
    ("libkml",              "libkml"),
    ("libmariadb",          "mariadb"),
    ("libmosquitto",        "mosquitto"),
    ("libnetcdf",           "netcdf"),
    ("libnuma",             "numactl"),
    ("libodbc",             "unixodbc"),
    ("libodbcinst",         "unixodbc"),
    ("libogdi",             "ogdi-dfsg"),
    ("libopencv",           "opencv"),
    ("libperl",             "perl"),
    ("libpoppler",          "poppler"),
    ("libproc",             "procps"),
    ("libprotobuf",         "protobuf"),
    ("libpython3",          "python3.11"),
    ("libqt5",              "qtbase-opensource-src"),
    ("libreadline",         "readline"),
    ("librtmp",             "rtmpdump"),
    ("librttopo",           "librttopo"),
    ("libsensors",          "lm-sensors"),
    ("libsocket",           "socket++"),
    ("libspatialite",       "spatialite"),
    ("libsuperlu",          "superlu"),
    ("libwebp",             "libwebp"),
    ("libx265",             "x265"),
    ("libxerces-c",         "xerces-c"),
    ("libz3",               "z3"),
    ("bindfs",              "bindfs"),
    ("ca-certificates",     "ca-certificates"),
    ("fuse",                "fuse"),
    ("mariadb",             "mariadb"),
    ("media-types",         "media-types"),
    ("mosquitto",           "mosquitto"),
    ("mysql-common",        "mariadb"),
    ("netbase",             "netbase"),
    ("perl",                "perl"),
    ("procps",              "procps"),
    ("python3.11",          "python3.11"),
    ("python3",             "python3.11"),
    ("readline-common",     "readline"),
    ("unixodbc-common",     "unixodbc"),
    ("wget",                "wget"),
]

# PyPI package name → GitHub source repository URL
PYPI_TO_GITHUB: dict[str, str] = {
    "bidict":           "https://github.com/jab/bidict",
    "certifi":          "https://github.com/certifi/python-certifi",
    "paho-mqtt":        "https://github.com/eclipse-paho/paho.mqtt.python",
    "plyfile":          "https://github.com/dranjan/python-plyfile",
    "psycopg2-binary":  "https://github.com/psycopg/psycopg2",
    "tqdm":             "https://github.com/tqdm/tqdm",
}

# Conan package name → GitHub source repository URL
CONAN_TO_GITHUB: dict[str, str] = {
    "autoconf":         "https://github.com/autotools-mirror/autoconf",
    "automake":         "https://github.com/autotools-mirror/automake",
    "eigen":            "https://github.com/eigenteam/eigen-git-mirror",
    "gnu-config":       "https://github.com/gcc-mirror/gcc",
    "libtool":          "https://github.com/autotools-mirror/libtool",
    "m4":               "https://github.com/autotools-mirror/m4",
    "paho-mqtt-c":      "https://github.com/eclipse/paho.mqtt.c",
    "paho-mqtt-cpp":    "https://github.com/eclipse/paho.mqtt.cpp",
}

# Other source repositories always included for compliance
OTHER_SOURCE_REPOS: list[str] = [
    "https://github.com/mozilla/geckodriver",
    "https://github.com/mirror/busybox",
]

# Base OS configuration for the sources Dockerfile
SOURCES_GRABBER_IMAGE = "debian:12"
SOURCES_FINAL_IMAGE = "debian:13"
SOURCES_DEB_SRC_REPOS = [
    "deb-src http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware",
    "deb-src http://security.debian.org/debian-security bookworm-security main",
    "deb-src http://deb.debian.org/debian bookworm-updates main",
    "deb-src http://deb.debian.org/debian trixie main contrib non-free non-free-firmware",
]


def _binary_to_source(binary_name: str) -> str:
    """Map a Debian binary package name to its source package name."""
    for prefix, source in DEB_BINARY_TO_SOURCE:
        if binary_name == prefix or binary_name.startswith(prefix + "-") or binary_name.startswith(prefix):
            return source
    return binary_name  # fall back to binary name itself


def _is_conan(component: str) -> bool:
    """Return True if the component is a Conan package (name/version format)."""
    return "/" in component and "==" not in component and ":" not in component


def generate_sources_dockerfile(gpllist: list[str], version_slug: str) -> str:
    """Generate the content of sources.Dockerfile for the current release.

    Derives the apt-get source list, Python git-clone list, and Conan
    git-clone list from the copyleft-licensed distributed packages in
    *gpllist*.
    """
    deb_sources: set[str] = set()
    pypi_clones: list[str] = []
    conan_clones: list[str] = []

    for component in gpllist:
        if "==" in component:
            pkg_name = component.split("==")[0]
            url = PYPI_TO_GITHUB.get(pkg_name)
            if url and url not in pypi_clones:
                pypi_clones.append(url)
        elif _is_conan(component):
            pkg_name = component.split("/")[0]
            url = CONAN_TO_GITHUB.get(pkg_name)
            if url and url not in conan_clones:
                conan_clones.append(url)
        else:
            base = component.split(":")[0]
            deb_sources.add(_binary_to_source(base))

    sorted_deb = sorted(deb_sources)
    sorted_pypi = sorted(pypi_clones)
    sorted_conan = sorted(conan_clones)

    lines: list[str] = [
        "# -*- mode: Fundamental; indent-tabs-mode: nil -*-",
        "",
        "# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation",
        "# SPDX-License-Identifier: Apache-2.0",
        "",
        "# Auto-generated by tools/dependencies/generate_dockerfile_artifacts.py",
        "# Run: make generate-dockerfile-zip",
        "",
        f"FROM {SOURCES_GRABBER_IMAGE} AS source-grabber",
        "",
    ]

    # Add deb-src repos as a single chained RUN
    for i, repo in enumerate(SOURCES_DEB_SRC_REPOS):
        prefix = "RUN " if i == 0 else "    && "
        suffix = " \\" if i < len(SOURCES_DEB_SRC_REPOS) - 1 else ""
        lines.append(f'{prefix}echo "{repo}" >> /etc/apt/sources.list{suffix}')
    lines.append("RUN apt-get update && apt-get install -y --no-install-recommends dpkg-dev")
    lines += ["", "WORKDIR /sources-deb", "RUN apt-get source --download-only \\"]

    for i, pkg in enumerate(sorted_deb):
        suffix = " \\" if i < len(sorted_deb) - 1 else ""
        lines.append(f"    {pkg}{suffix}")

    lines += [
        "",
        "WORKDIR /sources-python",
        "RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates git",
        "RUN : \\",
    ]
    for i, url in enumerate(sorted_pypi):
        suffix = " \\" if i < len(sorted_pypi) - 1 else ""
        lines.append(f"    ; git clone --depth 1 {url}{suffix}")

    if sorted_conan:
        lines += ["", "WORKDIR /sources-conan", "RUN : \\"]
        for i, url in enumerate(sorted_conan):
            suffix = " \\" if i < len(sorted_conan) - 1 else ""
            lines.append(f"    ; git clone --depth 1 {url}{suffix}")

    lines += ["", "WORKDIR /sources-other", "RUN : \\"]
    for i, url in enumerate(OTHER_SOURCE_REPOS):
        suffix = " \\" if i < len(OTHER_SOURCE_REPOS) - 1 else ""
        lines.append(f"    ; git clone --depth 1 {url}{suffix}")

    lines += [
        "",
        f"FROM {SOURCES_FINAL_IMAGE}",
        "",
        "COPY --from=source-grabber /sources* /sources",
        "COPY third-party-programs.txt /sources",
        "WORKDIR /sources",
        "",
        "USER nobody",
        "",
    ]

    return "\n".join(lines)


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


def find_deps_csv(data_dir: Path) -> Path:
    """Locate the dependencies CSV, preferring updated-dependencies.csv when present."""
    updated = data_dir / "updated-dependencies.csv"
    if updated.exists():
        return updated
    return find_latest_csv(data_dir, "*-Dependencies.csv")


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def generate_gpllist(deps: list[dict]) -> list[str]:
    """Collect unique component identifiers that have copyleft licenses and
    are distributed. Supports both 'Distributed by you?' (old) and
    'Distributed by you' (new) column names."""
    seen: set[str] = set()
    for row in deps:
        distributed = ""
        for col in _DISTRIBUTED_COLS:
            if col in row:
                distributed = row[col].strip().upper()
                break
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

                # Include requirements*.txt and conanfile.txt from the Dockerfile's directory
                for req in sorted(dockerfile_dir.glob("requirements*.txt")):
                    req_archive = f"{subfolder}/{req.name}"
                    zf.write(req, req_archive)
                    entries.append(req_archive)
                conanfile = dockerfile_dir / "conanfile.txt"
                if conanfile.exists():
                    conan_archive = f"{subfolder}/conanfile.txt"
                    zf.write(conanfile, conan_archive)
                    entries.append(conan_archive)

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
    parser.add_argument(
        "--no-update-sources",
        action="store_true",
        default=False,
        help="Skip regenerating sources.Dockerfile in the repo root",
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
    deps_path = args.deps or find_deps_csv(release_data_dir)
    print(f"Images  : {image_list_path}")
    print(f"Deps    : {deps_path}")

    images = load_csv(image_list_path)
    deps = load_csv(deps_path)

    # gpllist
    gpllist = generate_gpllist(deps)
    print(f"gpllist : {len(gpllist)} copyleft-licensed distributed packages")

    # Generate / update sources.Dockerfile
    if not args.no_update_sources:
        sources_content = generate_sources_dockerfile(gpllist, version_slug)
        sources_path = repo_root / "sources.Dockerfile"
        sources_path.write_text(sources_content, encoding="utf-8")
        print(f"\nUpdated : {sources_path}")

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
