#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration for VDMS adapter unit tests."""

import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_vdms():
  """Provide a mocked VDMS instance."""
  mock = MagicMock()
  return mock
