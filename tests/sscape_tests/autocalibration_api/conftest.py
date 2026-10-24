#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Local conftest for the autocalibration OpenAPI contract test.

Puts autocalibration/src on sys.path so the REST API module can be imported
directly on the host, without pulling in the native AprilTag extension
(kept out of the ``autocamcalib`` directory, which is excluded from host
collection for that reason).
"""

import sys
from pathlib import Path

_autocalibration_src = Path(__file__).resolve().parents[3] / "autocalibration" / "src"
if str(_autocalibration_src) not in sys.path:
  sys.path.insert(0, str(_autocalibration_src))
