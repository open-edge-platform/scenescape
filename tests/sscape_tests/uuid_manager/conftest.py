#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pytest configuration and fixtures for UUID manager tests.
Provides mock objects and test utilities.
"""

import pytest
from unittest.mock import MagicMock, Mock


@pytest.fixture
def mock_vdms():
  """
  Provides a mocked VDMS database instance.
  
  Returns:
    MagicMock: Mock VDMS instance with all methods available.
  """
  mock_instance = MagicMock()
  mock_instance.addSchema = Mock(return_value=({'status': 0}, []))
  mock_instance.findSchema = Mock(return_value=({'status': 0}, []))
  mock_instance.addEntry = Mock(return_value=({'status': 0}, []))
  mock_instance.findMatches = Mock(return_value=({'status': 0}, []))
  return mock_instance


@pytest.fixture
def mock_log():
  """
  Provides a mocked logger instance.
  
  Returns:
    MagicMock: Mock logger with all standard logging methods.
  """
  mock_logger = MagicMock()
  mock_logger.debug = Mock()
  mock_logger.info = Mock()
  mock_logger.warning = Mock()
  mock_logger.error = Mock()
  mock_logger.critical = Mock()
  return mock_logger


@pytest.fixture
def mock_milvus_adapter():
  """
  Provides a mocked Milvus adapter instance (optional dependency).
  
  Returns:
    MagicMock: Mock Milvus adapter with standard methods.
  """
  mock_instance = MagicMock()
  mock_instance.connect = Mock(return_value=True)
  mock_instance.addEntry = Mock(return_value=True)
  mock_instance.findMatches = Mock(return_value=[])
  return mock_instance
