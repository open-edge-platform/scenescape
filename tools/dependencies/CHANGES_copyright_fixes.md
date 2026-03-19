# Copyright Lookup Fixes — generate_third_party_programs.py

**Date:** 2026-03-19  
**File modified:** `tools/dependencies/generate_third_party_programs.py`

---

## Root Causes Addressed

### 1. PyPI — Case-Sensitive `project_urls` Key Lookup (was broken)

**Problem:** The code searched for `"Repository"`, `"Source Code"`, etc. as exact-case keys.
Real PyPI packages often use lowercase variants: `"repository"`, `"source code"`.
This caused many packages (e.g. `aiofiles`) to miss their GitHub URL entirely.

**Fix:** Convert `project_urls` dict to lowercase keys before searching the priority list.

---

### 2. PyPI — Version-Specific Query Had No Fallback

**Problem:** When querying `pypi.org/pypi/{name}/{version}/json` for an older or unreleased
version, the API sometimes returns no useful source links. There was no retry.

**Fix:** `_fetch_pypi_license_file()` now retries the project-level URL
(`pypi.org/pypi/{name}/json`) when a version-specific query yields no usable GitHub link.

---

### 3. PyPI — Only `LICENSE` File Was Tried

**Problem:** Many packages (e.g. `Flask`, `certifi`) have their license text in a file
whose path at HEAD differs, or the `LICENSE` file itself has no `Copyright` line (MPL-2.0,
pure MIT boilerplate, etc.). No fallback file types were attempted.

**Fix:** Extended the list of filenames tried per-repo to also include:
`NOTICE`, `NOTICE.txt`, `AUTHORS`, `AUTHORS.txt`  
These files frequently carry explicit copyright attribution when `LICENSE` does not.

---

### 4. PyPI — No Copyright Line Anywhere → No Result

**Problem:** For packages like `certifi` (MPL-2.0) and `cffi`, the LICENSE/NOTICE files
contain no line matching the copyright regex. Result was `"no copyright found"`.

**Fix:** `get_pypi_package_copyright()` now falls back to the PyPI JSON `author` metadata
field as a last resort and synthesises `"Copyright (c) {author}"` when no copyright line
is found in any fetched file.

---

### 5. Debian — Binary→Source Name Heuristic Missed Many Packages

**Problem:** `_debian_source_name_candidates()` used simple string manipulation
(strip trailing digits, strip `lib` prefix) which cannot resolve cases where the
source package name is completely different from the binary package name. Examples:

| Binary package   | Generated candidates              | Correct source |
|------------------|-----------------------------------|----------------|
| `libavcodec59`   | `libavcodec59`, `libavcodec`, … | `ffmpeg`       |
| `libpng16-16`    | `libpng16-16`, `libpng16-`, …  | `libpng`       |
| `libglib2.0-0`   | `libglib2.0-0`, …               | `glib2.0`      |
| `libpcre2-16-0`  | `libpcre2-16-0`, …              | `pcre2`        |
| `libsdl2-2.0-0`  | `libsdl2-2.0-0`, …             | `libsdl2`      |
| `libjbig0`       | `libjbig0`, `jbig0`, …         | `jbigkit`      |
| `gcc-14-base`    | `gcc-14-base`                   | `gcc-14`       |
| `libgcc-s1`      | `libgcc-s1`, `libgcc-s`, …     | `gcc-12`       |

**Fix:** Added `_DEBIAN_SOURCE_OVERRIDES` — a static dict with 90+ known
binary→source mappings covering:
- ffmpeg family (`libavcodec*`, `libavformat*`, `libswscale*`, …)
- libpng, glib2.0, gdk-pixbuf, pcre2/pcre3
- GCC runtime (`libgcc-s1`, `libstdc++6`, `gcc-12/13/14-base`, …)
- glibc (`libc6`)
- SDL2, vorbis, jbigkit, hdf4/5, lame, mpg123, unixodbc
- libxcb family, pango, harfbuzz, wayland, openal-soft, libva, …

`_debian_source_name_candidates()` checks this dict first; the heuristic is
used as fallback for everything else.

---

### 6. Debian/Ubuntu — Ubuntu Version Strings Not Matched Against Debian Versions

**Problem:** Ubuntu packages carry version strings like `14.2.0-4ubuntu2~24.04.1`.
When searching Debian's `sources.debian.org` API for a matching version the code
only stripped the Debian revision suffix (`-`), not the Ubuntu tilde suffix (`~`),
and it did not strip epoch prefixes like `1:`.

**Fix:** `_fetch_debian_copyright_for_source_pkg()` now:
1. Strips epoch prefix (`1:8.4.7+dfsg` → `8.4.7`)
2. Splits on `[-~+]` to extract the clean upstream version prefix
   (`14.2.0-4ubuntu2~24.04.1` → `14.2.0`)
3. Uses that prefix to find the best matching Debian source version

---

## New Symbols Added

| Symbol | Type | Purpose |
|--------|------|---------|
| `_DEBIAN_SOURCE_OVERRIDES` | `dict` | Static binary→source package name overrides (90+ entries) |

## Functions Modified

| Function | Change summary |
|----------|---------------|
| `_fetch_pypi_license_file()` | Case-insensitive key lookup; version fallback retry; added NOTICE/AUTHORS to filenames |
| `get_pypi_package_copyright()` | Author-field fallback when no copyright line found |
| `_debian_source_name_candidates()` | Checks `_DEBIAN_SOURCE_OVERRIDES` first |
| `_fetch_debian_copyright_for_source_pkg()` | Epoch + Ubuntu version prefix stripping |
