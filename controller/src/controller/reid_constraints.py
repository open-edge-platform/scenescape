# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compatibility alias for standalone Re-ID query constraints."""

import sys

from reid_service import reid_constraints as _implementation

sys.modules[__name__] = _implementation
