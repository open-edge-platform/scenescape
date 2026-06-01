# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

_adapter_src = Path(__file__).resolve().parents[3] / "dlstreamer-pipeline-server" / "user_scripts" / "gvapython" / "sscape"
if str(_adapter_src) not in sys.path:
  sys.path.insert(0, str(_adapter_src))
