#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared bootstrap for OpenAPI contract tests under this directory.

Puts the mapping and autocalibration source trees on ``sys.path`` so their
Flask apps can be imported on the host. The repository root is discovered
from ``version.txt``; do not count parent directories.
"""

import sys

from tests.sscape_tests.api.common import repo_root

_ROOT = repo_root(__file__)
for _relative in ("mapping/src", "autocalibration/src"):
  _src = _ROOT / _relative
  if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
