# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compatibility alias for the standalone VDMS adapter."""

import sys

from reid_service import vdms_adapter as _implementation

sys.modules[__name__] = _implementation
