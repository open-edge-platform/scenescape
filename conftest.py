# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Root-level conftest — excludes satellite test suites from collection when
# pytest runs from the repo root (e.g. VS Code test discovery).
# These suites have dependencies only available inside Docker containers.

collect_ignore_glob = [
    "autocalibration/*",
    "mapping/*",
    "tools/*",
    "tracker/*",
    "tests/api/*",
    "tests/perf_tests/*",
    "tests/system/metric/*",
    "tests/pipeline_runner/*",
    "tests/ntlb/*",
]
