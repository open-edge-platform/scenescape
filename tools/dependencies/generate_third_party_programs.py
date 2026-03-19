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

# Global cache for per-package copyright statements
_copyright_cache = {}

# Global cache for full license file texts fetched from package sources
_package_license_file_cache = {}


def extract_copyright_from_text(text):
    """
    Extract copyright statements from the text of a LICENSE file.

    Matches lines that start with "Copyright" (case-insensitive), optionally
    followed by (c) or the © symbol.
    """
    copyright_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if re.match(r"(?i)^copyright\s*[\(\u00a9]", stripped) or \
           re.match(r"(?i)^copyright\s+\d{4}", stripped) or \
           re.match(r"(?i)^copyright\s+\(c\)", stripped):
            copyright_lines.append(stripped)
    return copyright_lines


def _get_github_repo_path(github_url):
    """Extract the 'owner/repo' path from a GitHub URL."""
    match = re.match(r"https?://github\.com/([^/]+/[^/?#]+?)(?:\.git|[/?#].*)?$", github_url)
    if match:
        return match.group(1)
    return None


def _fetch_pypi_license_file(package_name, version=None):
    """
    Fetch the raw LICENSE file text from a PyPI package's GitHub source repository.

    Strategy:
      1. Query the PyPI JSON API to find the project source URL.
      2. Resolve to a GitHub repository.
      3. Try common LICENSE file names and return the first one found.

    Results are cached in _package_license_file_cache.
    Returns the full license file text, or None if not found.
    """
    cache_key = (package_name, version)
    if cache_key in _package_license_file_cache:
        return _package_license_file_cache[cache_key]

    # Query PyPI JSON API
    if version:
        api_url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    else:
        api_url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        resp = requests.get(api_url, timeout=10)
        if resp.status_code != 200:
            _package_license_file_cache[cache_key] = None
            return None
        data = resp.json()
    except Exception:
        _package_license_file_cache[cache_key] = None
        return None

    info = data.get("info", {})
    project_urls = info.get("project_urls") or {}
    home_page = (info.get("home_page") or "").strip()

    # Search for a GitHub URL across common project_url keys
    github_url = None
    source_key_priority = ["Source Code", "Source", "Repository", "GitHub", "Code", "Homepage", "Home"]
    for key in source_key_priority:
        val = (project_urls.get(key) or "").strip()
        if "github.com" in val:
            github_url = val
            break
    if not github_url and "github.com" in home_page:
        github_url = home_page

    if not github_url:
        _package_license_file_cache[cache_key] = None
        return None

    repo_path = _get_github_repo_path(github_url)
    if not repo_path:
        _package_license_file_cache[cache_key] = None
        return None

    # Try common LICENSE file names in the default branch
    license_filenames = ["LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE.rst",
                         "LICENCE", "COPYING", "COPYING.txt"]
    for filename in license_filenames:
        raw_url = f"https://raw.githubusercontent.com/{repo_path}/HEAD/{filename}"
        try:
            resp = requests.get(raw_url, timeout=10)
            if resp.status_code == 200:
                _package_license_file_cache[cache_key] = resp.text
                return resp.text
        except Exception:
            continue

    _package_license_file_cache[cache_key] = None
    return None


def get_pypi_package_copyright(package_name, version=None):
    """
    Fetch copyright statement(s) from a PyPI package's source repository.
    Returns a newline-joined string of copyright lines, or None if not found.
    """
    cache_key = f"pypi:{package_name}:{version}"
    if cache_key in _copyright_cache:
        return _copyright_cache[cache_key]

    license_text = _fetch_pypi_license_file(package_name, version)
    if license_text is None:
        _copyright_cache[cache_key] = None
        return None

    copyright_lines = extract_copyright_from_text(license_text)
    if copyright_lines:
        result = "\n".join(copyright_lines)
        _copyright_cache[cache_key] = result
        return result

    _copyright_cache[cache_key] = None
    return None


def get_pypi_package_license_text(package_name, version=None):
    """
    Fetch the full license text from a PyPI package's source repository on GitHub.
    Returns the full text of the LICENSE file, or None if not found.
    """
    return _fetch_pypi_license_file(package_name, version)


def _parse_pypi_component(component):
    """Parse 'package==version' / 'package>=version' / 'package' into (name, version)."""
    match = re.match(r"^([A-Za-z0-9_.\-]+)(?:[><=!~^]+([A-Za-z0-9._\-]*))?$", component)
    if match:
        return match.group(1), match.group(2) or None
    return None, None


def _parse_debian_component(component):
    """
    Parse a Debian binary package component string into (name, version).

    Component format from the CSV is 'pkg:version' or 'pkg:arch:version'.
    The architecture qualifier (amd64, i386, arm64, …) is discarded.
    """
    parts = component.split(":")
    name = parts[0]
    if len(parts) >= 3:
        version = parts[-1]
    elif len(parts) == 2:
        # Second field is a version if it contains digits or version separators;
        # otherwise it is an architecture name with no version present.
        if re.match(r'[0-9]|.*[.+~]', parts[1]):
            version = parts[1]
        else:
            version = None
    else:
        version = None
    return name, version


def _parse_conan_component(component):
    """
    Parse a Conan component string 'name/version[@user/channel]' into (name, version).
    """
    at_stripped = component.split("@")[0]
    parts = at_stripped.split("/")
    name = parts[0]
    version = parts[1] if len(parts) > 1 else None
    return name, version


def _extract_dep5_copyrights(text):
    """
    Extract copyright statements from a Debian DEP-5 debian/copyright file.

    Parses the structured 'Copyright:' fields (including multi-line continuation
    lines) from all Files stanzas.  Falls back to the generic regex extractor
    for old-style free-form copyright files.

    Returns a list of unique copyright statement strings.
    """
    dep5_copyrights = []
    current_lines = []
    in_copyright_field = False

    for line in text.split("\n"):
        if re.match(r"^Copyright:\s*", line, re.IGNORECASE):
            # Flush previous field
            dep5_copyrights.extend(current_lines)
            current_lines = []
            value = re.sub(r"^Copyright:\s*", "", line, flags=re.IGNORECASE).strip()
            if value and value != ".":
                current_lines.append(value)
            in_copyright_field = True
        elif in_copyright_field and line.startswith((" ", "\t")):
            value = line.strip()
            if value and value != ".":
                current_lines.append(value)
        else:
            dep5_copyrights.extend(current_lines)
            current_lines = []
            in_copyright_field = False

    dep5_copyrights.extend(current_lines)

    # Deduplicate, preserving order
    seen = set()
    unique = []
    for c in dep5_copyrights:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    if unique:
        return unique

    # Old-style free-form copyright file – fall back to regex
    return extract_copyright_from_text(text)


def _debian_source_name_candidates(binary_name):
    """
    Generate source package name candidates from a Debian binary package name.

    Debian binary packages often have names like 'libbrotli1' while the source
    package is 'brotli'.  Common patterns are tried in order:
      1. Exact match (binary name == source name)
      2. Strip trailing digits (libbrotli1 -> libbrotli)
      3. Strip leading 'lib' prefix + trailing digits (libbrotli1 -> brotli)
    """
    candidates = [binary_name]
    # Strip trailing version digit(s): libfoo2 -> libfoo
    no_digits = re.sub(r'\d+$', '', binary_name)
    if no_digits and no_digits != binary_name:
        candidates.append(no_digits)
    # Strip leading 'lib' prefix
    if binary_name.startswith('lib'):
        no_lib = binary_name[3:]
        if no_lib and no_lib not in candidates:
            candidates.append(no_lib)
        no_lib_no_digits = re.sub(r'\d+$', '', no_lib)
        if no_lib_no_digits and no_lib_no_digits not in candidates:
            candidates.append(no_lib_no_digits)
    return candidates


def _fetch_debian_copyright_file(package_name, version):
    """
    Fetch the debian/copyright file for a package from sources.debian.org.

    Uses the source package name (often identical to the binary name) and
    selects the best available source version.  Results are cached.
    Returns the raw copyright file text, or None if not found.
    """
    cache_key = f"deb-copyright:{package_name}:{version}"
    if cache_key in _package_license_file_cache:
        return _package_license_file_cache[cache_key]

    # Try source package name candidates (binary name often differs from source name,
    # e.g. 'libbrotli1' binary comes from 'brotli' source package).
    for src_pkg in _debian_source_name_candidates(package_name):
        text = _fetch_debian_copyright_for_source_pkg(src_pkg, version)
        if text is not None:
            _package_license_file_cache[cache_key] = text
            return text

    _package_license_file_cache[cache_key] = None
    return None


def _fetch_debian_copyright_for_source_pkg(package_name, version):
    """Fetch debian/copyright for a specific *source* package name (no caching)."""
    # Retrieve available source package versions
    api_url = f"https://sources.debian.org/api/src/{package_name}/"
    try:
        resp = requests.get(api_url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("error"):
            return None
    except Exception:
        return None

    versions = [v["version"] for v in data.get("versions", [])]
    if not versions:
        return None

    # Pick the best matching version: exact first, then upstream-prefix match, then latest
    src_version = None
    if version and version in versions:
        src_version = version
    else:
        upstream_ver = version.split("-")[0] if version else ""
        for v in versions:
            if upstream_ver and v.startswith(upstream_ver):
                src_version = v
                break
        if not src_version:
            src_version = versions[0]  # newest listed first

    copyright_url = (
        f"https://sources.debian.org/api/src/{package_name}/{src_version}/debian/copyright/"
    )
    try:
        resp = requests.get(copyright_url, timeout=10)
        if resp.status_code == 200:
            meta = resp.json()
            raw_path = meta.get("raw_url", "")
            if raw_path:
                raw_resp = requests.get(f"https://sources.debian.org{raw_path}", timeout=10)
                if raw_resp.status_code == 200:
                    return raw_resp.text
    except Exception:
        pass

    return None


def get_debian_package_copyright(package_name, version=None):
    """
    Extract copyright statements from a Debian package's debian/copyright file.
    Returns a newline-joined string of copyright lines, or None if not found.
    """
    cache_key = f"deb-cpy:{package_name}:{version}"
    if cache_key in _copyright_cache:
        return _copyright_cache[cache_key]

    text = _fetch_debian_copyright_file(package_name, version)
    if text is None:
        _copyright_cache[cache_key] = None
        return None

    copyright_lines = _extract_dep5_copyrights(text)
    if copyright_lines:
        result = "\n".join(copyright_lines)
        _copyright_cache[cache_key] = result
        return result

    _copyright_cache[cache_key] = None
    return None


def _fetch_conan_license_file(package_name, version=None):
    """
    Fetch the upstream LICENSE file for a Conan Center package.

    Strategy:
      1. Locate the conanfile.py in the conan-center-index GitHub repository.
      2. Extract the 'homepage' or 'url' attribute to find the upstream repo.
      3. Download the LICENSE file from the upstream repository on GitHub.

    Results are cached.  Returns the full license text, or None if not found.
    """
    cache_key = (f"conan:{package_name}", version)
    if cache_key in _package_license_file_cache:
        return _package_license_file_cache[cache_key]

    # conan-center-index uses 'all/' subfolder for packages with a single recipe
    # and version-named subfolders for packages with per-version recipes.
    conanfile_candidates = [
        f"https://raw.githubusercontent.com/conan-io/conan-center-index/master/recipes/{package_name}/all/conanfile.py",
    ]
    if version:
        conanfile_candidates.append(
            f"https://raw.githubusercontent.com/conan-io/conan-center-index/master/recipes/{package_name}/{version}/conanfile.py"
        )

    conanfile_text = None
    for url in conanfile_candidates:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                conanfile_text = resp.text
                break
        except Exception:
            continue

    if not conanfile_text:
        _package_license_file_cache[cache_key] = None
        return None

    # Extract the upstream project homepage from the conanfile.
    # We deliberately avoid the 'url' attribute because it conventionally points
    # to the conan-center-index repository itself, not the upstream project.
    github_url = None
    homepage_match = re.search(r'homepage\s*=\s*["\']([^"\']+)["\']', conanfile_text)
    if homepage_match:
        val = homepage_match.group(1).strip()
        if "github.com" in val:
            github_url = val

    if not github_url:
        _package_license_file_cache[cache_key] = None
        return None

    repo_path = _get_github_repo_path(github_url)
    if not repo_path:
        _package_license_file_cache[cache_key] = None
        return None

    license_filenames = ["LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE.rst",
                         "LICENCE", "COPYING", "COPYING.txt"]
    for filename in license_filenames:
        raw_url = f"https://raw.githubusercontent.com/{repo_path}/HEAD/{filename}"
        try:
            resp = requests.get(raw_url, timeout=10)
            if resp.status_code == 200:
                _package_license_file_cache[cache_key] = resp.text
                return resp.text
        except Exception:
            continue

    _package_license_file_cache[cache_key] = None
    return None


def get_conan_package_copyright(package_name, version=None):
    """
    Extract copyright statements from a Conan package's upstream LICENSE file.
    Returns a newline-joined string of copyright lines, or None if not found.
    """
    cache_key = f"conan-cpy:{package_name}:{version}"
    if cache_key in _copyright_cache:
        return _copyright_cache[cache_key]

    text = _fetch_conan_license_file(package_name, version)
    if text is None:
        _copyright_cache[cache_key] = None
        return None

    copyright_lines = extract_copyright_from_text(text)
    if copyright_lines:
        result = "\n".join(copyright_lines)
        _copyright_cache[cache_key] = result
        return result

    _copyright_cache[cache_key] = None
    return None


def get_package_copyright(component, origin):
    """
    Get copyright statement(s) for a package based on its declared origin.

    Supported origins:
      - pypi    : queries PyPI JSON API → GitHub upstream LICENSE file
      - debian  : queries sources.debian.org → debian/copyright (DEP-5)
      - ubuntu  : same as debian (Ubuntu packages are sourced from Debian)
      - conan   : queries conan-center-index → upstream GitHub LICENSE file

    Returns a newline-joined string of copyright lines, or None if not found.
    """
    if not origin:
        return None
    origin_lower = origin.lower().strip()
    if origin_lower == "pypi":
        package_name, version = _parse_pypi_component(component)
        if package_name:
            return get_pypi_package_copyright(package_name, version)
    elif origin_lower in ("debian", "ubuntu"):
        package_name, version = _parse_debian_component(component)
        if package_name:
            return get_debian_package_copyright(package_name, version)
    elif origin_lower == "conan":
        package_name, version = _parse_conan_component(component)
        if package_name:
            return get_conan_package_copyright(package_name, version)
    return None


def get_package_license_text(component, origin):
    """
    Get the full license file text for a package from its source repository.

    Supported origins:
      - pypi  : fetches the LICENSE file from the project's GitHub repository.
      - conan : fetches the upstream LICENSE file via conan-center-index metadata.

    Debian/Ubuntu packages use the SPDX template for the license body; their
    copyright statements are surfaced separately via get_package_copyright().

    Returns the full license text string, or None if not available.
    """
    if not origin:
        return None
    origin_lower = origin.lower().strip()
    if origin_lower == "pypi":
        package_name, version = _parse_pypi_component(component)
        if package_name:
            return get_pypi_package_license_text(package_name, version)
    elif origin_lower == "conan":
        package_name, version = _parse_conan_component(component)
        if package_name:
            return _fetch_conan_license_file(package_name, version)
    return None


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
        "Apache Software License": spdx_base + "Apache-2.0.txt",  # Generic Apache maps to 2.0
        "Artistic License": spdx_base + "Artistic-2.0.txt",
        "Artistic License 1.0": spdx_base + "Artistic-1.0.txt",
        "BSD": spdx_base + "BSD-3-Clause.txt",  # Generic BSD maps to 3-clause
        "BSD License": spdx_base + "BSD-3-Clause.txt",  # Generic BSD maps to 3-clause
        "BSD 2-Clause \"Simplified\" License": spdx_base + "BSD-2-Clause.txt",

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
        "MIT-License": spdx_base + "MIT.txt",
        "OpenLDAP Public License": spdx_base + "OLDAP-2.8.txt",  # Completely different name
        "PIL": spdx_base + "HPND.txt",  # PIL uses HPND license
        "PSF": spdx_base + "Python-2.0.txt",  # PSF -> Python-2.0
        "SIL Open Font License": spdx_base + "OFL-1.1.txt",  # Completely different name

        # ── LicenseRef-* mappings ─────────────────────────────────────────────
        # These are non-SPDX identifiers (e.g. from Debian/Ubuntu copyright
        # databases, Scancode, or hand-curated metadata) mapped to the closest
        # canonical SPDX license text.

        # Apache variants
        "LicenseRef-Apache": spdx_base + "Apache-2.0.txt",
        "LicenseRef-Apache-2.0-": spdx_base + "Apache-2.0.txt",       # trailing dash artifact
        "LicenseRef-Apache-License-2.0": spdx_base + "Apache-2.0.txt",  # verbose alias
        "LicenseRef-xerces-Apache-2.0": spdx_base + "Apache-2.0.txt",

        # Artistic
        "LicenseRef-Artistic": spdx_base + "Artistic-2.0.txt",

        # BSD-1-clause
        "LicenseRef-BSD-1-clause-UCB": spdx_base + "BSD-1-Clause.txt",

        # BSD-2-clause variants
        "LicenseRef-BSD-2": spdx_base + "BSD-2-Clause.txt",
        "LicenseRef-BSD-2-clause-beyond": spdx_base + "BSD-2-Clause.txt",
        "LicenseRef-NRL-2-clause": spdx_base + "BSD-2-Clause.txt",

        # BSD-3-clause variants (all map to canonical BSD-3-Clause text)
        "LicenseRef-BSD-3-Clause-Google": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-Berkeley": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-Carnegie": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-GENERIC": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-Google": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-Oracle": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-UCB": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-WIDE": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-alike-Alexander-Chemeris": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-alike-CREATIS": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-alike-Jan-de-Vaan": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-alike-Mathieu-Malaterre": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-alike-Theodore-Ts": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-carnegie": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-chromium": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-cmake": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-kitware": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-3-clause-with-weird-numbering": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-Author": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-BY-LC-NE": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD-like-Spencer": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BSD3": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-BrownUn-UnCalifornia-ErikCorry": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-Carnegie": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-Chromium-BSD-style": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-CORE-MATH": spdx_base + "BSD-3-Clause.txt",       # CORE-MATH uses BSD-3
        "LicenseRef-EDL-1.0": spdx_base + "BSD-3-Clause.txt",         # Eclipse Dist. License ≈ BSD-3
        "LicenseRef-HSIEH-BSD": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-HSIEH-DERIVATIVE": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-Hybrid-BSD": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-JMVBSD": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-KISSFFTBSD": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-NRL-3-clause": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-PCRE": spdx_base + "BSD-3-Clause.txt",            # PCRE uses BSD-3
        "LicenseRef-REGCOMP": spdx_base + "BSD-3-Clause.txt",         # Henry Spencer regex (BSD-like)
        "LicenseRef-REGCOMP-": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-STEREO-CALIB-PERMISSIVE": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-brg-endian": spdx_base + "BSD-3-Clause.txt",      # Brian Gladman permissive
        "LicenseRef-cipic": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-cpl-mem-cache": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-gdcmjpeg": spdx_base + "BSD-3-Clause.txt",
        "LicenseRef-hidapi-orig": spdx_base + "BSD-3-Clause.txt",     # HIDAPI original = BSD-3
        "LicenseRef-imath": spdx_base + "BSD-3-Clause.txt",           # OpenEXR/iMath = BSD-3
        "LicenseRef-permissive-colamd": spdx_base + "BSD-3-Clause.txt",  # COLAMD = BSD-3
        "LicenseRef-u-o-tennesee": spdx_base + "BSD-3-Clause.txt",    # Univ. of Tennessee (LAPACK)

        # BSD-4-clause variants (original 4-clause with advertising clause)
        "LicenseRef-BSD-124-clause-UCB": spdx_base + "BSD-4-Clause.txt",  # 1+2+4-clause UCB
        "LicenseRef-BSD-4-clause-POWERDOG": spdx_base + "BSD-4-Clause.txt",
        "LicenseRef-BSD-4-clause-UCB": spdx_base + "BSD-4-Clause.txt",

        # Boost Software License 1.0
        "LicenseRef-BSL": spdx_base + "BSL-1.0.txt",
        "LicenseRef-Boost": spdx_base + "BSL-1.0.txt",
        "LicenseRef-Boost-1.0": spdx_base + "BSL-1.0.txt",

        # bzip2
        "LicenseRef-BZIP": spdx_base + "bzip2-1.0.6.txt",

        # Bitstream Vera
        "LicenseRef-Bitstream": spdx_base + "Bitstream-Vera.txt",

        # Public domain / CC0
        "LicenseRef-Base64": spdx_base + "CC0-1.0.txt",               # Base64 code is public domain
        "LicenseRef-CC-zero-waive-1.0-us": spdx_base + "CC0-1.0.txt",
        "LicenseRef-CC0": spdx_base + "CC0-1.0.txt",
        "LicenseRef-PD": spdx_base + "CC0-1.0.txt",
        "LicenseRef-Public-Domain": spdx_base + "CC0-1.0.txt",
        "LicenseRef-Public-domain": spdx_base + "CC0-1.0.txt",
        "LicenseRef-PublicDomain-David-Ludwig": spdx_base + "CC0-1.0.txt",
        "LicenseRef-PublicDomain-Edgar-Simo": spdx_base + "CC0-1.0.txt",
        "LicenseRef-PublicDomain-Sam-Lantinga": spdx_base + "CC0-1.0.txt",
        "LicenseRef-SDBM-PUBLIC-DOMAIN": spdx_base + "CC0-1.0.txt",
        "LicenseRef-Spherepack": spdx_base + "CC0-1.0.txt",           # NCAR public domain
        "LicenseRef-dlmalloc": spdx_base + "CC0-1.0.txt",             # dlmalloc is public domain
        "LicenseRef-public-domain": spdx_base + "CC0-1.0.txt",
        "LicenseRef-public-domain-Kroon": spdx_base + "CC0-1.0.txt",

        # FSF All-Permissive (FSFAP)
        "LicenseRef-FSF-unlimited": spdx_base + "FSFAP.txt",
        "LicenseRef-GNU-All-Permissive-License": spdx_base + "FSFAP.txt",
        "LicenseRef-GNU-All-Permissive-License-FSF": spdx_base + "FSFAP.txt",
        "LicenseRef-permissive-configure": spdx_base + "FSFAP.txt",   # autoconf configure scripts
        "LicenseRef-permissive-fsf": spdx_base + "FSFAP.txt",
        "LicenseRef-unlimited-free-doc": spdx_base + "FSFAP.txt",

        # GFDL (no invariant sections variant)
        "LicenseRef-GFDL-NIV-1.3": spdx_base + "GFDL-1.3-no-invariants-only.txt",

        # GPL variants (use base GPL text; exception clauses are noted separately)
        "LicenseRef-GPL": spdx_base + "GPL-2.0-only.txt",
        "LicenseRef-GPL-2--with-bison-exception": spdx_base + "GPL-2.0-only.txt",
        "LicenseRef-GPL-2--with-link-exception": spdx_base + "GPL-2.0-only.txt",
        "LicenseRef-GPL-2-either": spdx_base + "GPL-2.0-or-later.txt",
        "LicenseRef-GPL-2-or": spdx_base + "GPL-2.0-or-later.txt",
        "LicenseRef-GPL-3--WITH-BISON-EXCEPTION": spdx_base + "GPL-3.0-only.txt",
        "LicenseRef-GPL-3--with-bison-exception": spdx_base + "GPL-3.0-only.txt",
        "LicenseRef-GPLWithACException": spdx_base + "GPL-2.0-only.txt",  # WITH Autoconf exception
        "LicenseRef-GPLv3-": spdx_base + "GPL-3.0-only.txt",
        "LicenseRef-DONT-CHANGE-THE-GPL": spdx_base + "GPL-2.0-only.txt",

        # HPND variants (Historical Permission Notice and Disclaimer)
        "LicenseRef-HPND-3i": spdx_base + "HPND.txt",
        "LicenseRef-HPND-disclaimer": spdx_base + "HPND.txt",
        "LicenseRef-HPND-eos": spdx_base + "HPND.txt",
        "LicenseRef-HPND-p-sl-sgi": spdx_base + "HPND.txt",
        "LicenseRef-HPND-sl-gl-sgi": spdx_base + "HPND.txt",
        "LicenseRef-HPND-sl-sgi": spdx_base + "HPND.txt",
        "LicenseRef-gsm": spdx_base + "HPND.txt",                     # libgsm "use freely" = HPND-like

        # IBM Public License
        "LicenseRef-IBM": spdx_base + "IPL-1.0.txt",

        # ISC
        "LicenseRef-ISC-License": spdx_base + "ISC.txt",
        "LicenseRef-ISC-packaging": spdx_base + "ISC.txt",

        # libjpeg / IJG
        "LicenseRef-libjpeg": spdx_base + "IJG.txt",

        # LGPL variants
        "LicenseRef-LGPL-2.1--OpenSSL": spdx_base + "LGPL-2.1-only.txt",
        "LicenseRef-LGPL-2.1--with-link-exception": spdx_base + "LGPL-2.1-only.txt",
        "LicenseRef-LGPLv2.1-": spdx_base + "LGPL-2.1-only.txt",
        "LicenseRef-LGPLv3--or-GPLv2-": spdx_base + "LGPL-3.0-or-later.txt",
        "LicenseRef-LPGL-2.1-": spdx_base + "LGPL-2.1-only.txt",     # typo: LPGL = LGPL

        # Lucent Public License
        "LicenseRef-lucent": spdx_base + "LPL-1.0.txt",

        # MIT / Expat variants
        "LicenseRef-Expat": spdx_base + "MIT.txt",                    # Expat is the MIT license
        "LicenseRef-Expat-advertising": spdx_base + "MIT.txt",
        "LicenseRef-Expat-like": spdx_base + "MIT.txt",
        "LicenseRef-Gareth-McCaughan": spdx_base + "MIT.txt",
        "LicenseRef-Harfbuzz": spdx_base + "MIT.txt",
        "LicenseRef-Inner-Net": spdx_base + "MIT.txt",                # Inner Net License ≈ MIT
        "LicenseRef-MIT-FSF-public": spdx_base + "MIT.txt",
        "LicenseRef-MIT-X11": spdx_base + "MIT.txt",                  # X11 variant of MIT
        "LicenseRef-MIT-like-Lord": spdx_base + "MIT.txt",
        "LicenseRef-RRA-KEEP-THIS-NOTICE": spdx_base + "MIT.txt",     # Russ Allbery permissive
        "LicenseRef-SGI": spdx_base + "MIT.txt",                      # SGI X11/MIT-style
        "LicenseRef-X11-install-sh": spdx_base + "MIT.txt",
        "LicenseRef-fontconfig": spdx_base + "MIT.txt",
        "LicenseRef-mit-kemar": spdx_base + "MIT.txt",
        "LicenseRef-ncxml": spdx_base + "MIT.txt",
        "LicenseRef-permissive": spdx_base + "MIT.txt",               # generic permissive ≈ MIT
        "LicenseRef-permissive1": spdx_base + "MIT.txt",
        "LicenseRef-permissive2": spdx_base + "MIT.txt",

        # Mozilla permissive
        "LicenseRef-Mozilla-permissive": spdx_base + "MPL-2.0.txt",

        # OpenSSL / SSLeay combined
        "LicenseRef-OpenSSL-SSLeay": spdx_base + "OpenSSL.txt",

        # RSA Data Security (MD4/MD5 notice)
        "LicenseRef-RSA-Data-Security": spdx_base + "RSA-MD.txt",

        # SGI Free Software License B
        "LicenseRef-SGI-Free-Software-License-B": spdx_base + "SGI-B-2.0.txt",

        # Unicode
        "LicenseRef-Unicode": spdx_base + "Unicode-DFS-2016.txt",
        "LicenseRef-Unicode-data": spdx_base + "Unicode-DFS-2016.txt",

        # WTFPL
        "LicenseRef-WTFPL-2": spdx_base + "WTFPL.txt",

        # Zlib / libpng
        "LicenseRef-zlib-libpng": spdx_base + "Zlib.txt",
        "LicenseRef-zlib-libpng-like-permissive": spdx_base + "Zlib.txt",
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
    component_to_origin = {}  # component -> origin (first occurrence wins)

    # Read dependencies CSV
    with open(input_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            component = row["Component"].strip()
            license_ = row["License"].strip()
            origin = row.get("Origin", "").strip()
            components.append((component, license_))
            # Record origin for copyright lookup (first occurrence wins)
            if component not in component_to_origin:
                component_to_origin[component] = origin
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

    # -- Collect per-component copyright statements --
    # Build the set of unique components we need to look up
    all_unique_components = set()
    for comps in license_expr_to_components.values():
        all_unique_components.update(comps)

    print("\nFetching copyright statements from package sources...")
    component_copyrights = {}  # component -> copyright text (or None)
    for comp in sorted(all_unique_components):
        origin = component_to_origin.get(comp, "")
        copyright_text = get_package_copyright(comp, origin)
        if copyright_text:
            component_copyrights[comp] = copyright_text
            print(f"  OK  {comp}: {copyright_text.splitlines()[0]}")
        else:
            print(f"  --  {comp}: no copyright found")

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
            print(f"Processing license expression: {license_expr}")

            # Prefer full license text fetched directly from a package source.
            # Use the first component in the group that has a retrievable LICENSE file.
            license_text = None
            pkg_license_source = None
            for comp in license_expr_to_components[license_expr]:
                origin = component_to_origin.get(comp, "")
                pkg_text = get_package_license_text(comp, origin)
                if pkg_text:
                    license_text = pkg_text
                    pkg_license_source = comp
                    break

            if pkg_license_source:
                print(f"  Using license text from package source: {pkg_license_source}")
            else:
                # Fall back to SPDX template / local files
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
                    # Include per-component copyright statement when the license text
                    # comes from a different component or from the SPDX template
                    # (the copyright for pkg_license_source is embedded in its LICENSE file).
                    if comp in component_copyrights and comp != pkg_license_source:
                        for cline in component_copyrights[comp].splitlines():
                            f.write(f"        {cline}\n")
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
