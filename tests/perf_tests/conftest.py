# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

_perf_tests_dir = str(Path(__file__).resolve().parent)
if _perf_tests_dir not in sys.path:
  sys.path.insert(0, _perf_tests_dir)
