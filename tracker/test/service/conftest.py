# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration for service tests."""

import warnings


def pytest_configure(config):
    """Configure warning filters for cleaner output."""
    # Show ServiceTestWarning without source code line
    warnings.filterwarnings("always", category=UserWarning, module="test_tracker_service")
