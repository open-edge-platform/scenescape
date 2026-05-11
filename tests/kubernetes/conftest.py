# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
conftest.py for tests/kubernetes/

Forces --backend=kubernetes for every test in this directory so that the
VS Code Test Extension and plain `pytest tests/kubernetes/` work without
having to pass the flag manually.
"""


def pytest_configure(config):
  # Only override if the user has not already set a non-default backend.
  if config.getoption("--backend", default="docker") == "docker":
    config.option.backend = "kubernetes"
