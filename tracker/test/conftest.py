# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration - re-exports fixtures from service_tests package.

This allows pytest to discover fixtures when running tests from the test/ directory.
"""

# Re-export fixtures from service_tests package
from service_tests.config import test_config
from service_tests.infrastructure import docker_compose

# Make fixtures available to pytest
__all__ = ["test_config", "docker_compose"]
