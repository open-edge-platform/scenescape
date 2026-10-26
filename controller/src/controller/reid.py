# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compatibility alias for the standalone Re-ID package."""

import sys

from reid import reid as _implementation

sys.modules[__name__] = _implementation
