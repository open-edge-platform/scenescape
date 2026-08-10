#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared fixtures for cluster_analytics unit tests.

Adds cluster_analytics/src to sys.path so modules can be imported
directly without Docker or a container install.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLUSTER_SRC = _REPO_ROOT / "cluster_analytics" / "src"

if str(_CLUSTER_SRC) not in sys.path:
  sys.path.insert(0, str(_CLUSTER_SRC))

_SCENE_COMMON_SRC = _REPO_ROOT / "scene_common" / "src"

if str(_SCENE_COMMON_SRC) not in sys.path:
  sys.path.insert(0, str(_SCENE_COMMON_SRC))
  # Evict any namespace-package stub so the real package is re-resolved
  sys.modules.pop("scene_common", None)

CONFIG_PATH = str(_REPO_ROOT / "cluster_analytics" / "config" / "config.json")


@pytest.fixture(scope="session")
def config_path():
  return CONFIG_PATH


@pytest.fixture
def config():
  from cluster_analytics_context import ClusterAnalyticsConfig
  return ClusterAnalyticsConfig(config_path=CONFIG_PATH)


@pytest.fixture
def context():
  with patch("cluster_analytics_context.PubSub") as mock_pubsub, \
       patch("cluster_analytics_context.ClusterTracker") as mock_tracker:
    mock_pubsub.return_value.connect.return_value = None
    from cluster_analytics_context import ClusterAnalyticsContext
    ctx = ClusterAnalyticsContext(
      broker="localhost",
      broker_auth="",
      cert=None,
      root_cert=None,
      enable_webui=False,
    )
    ctx.client = None
    yield ctx


@pytest.fixture
def make_objects():
  def _make(positions, category="person", base_velocity=None):
    """Create fake detection objects at given (x, y) positions."""
    if base_velocity is None:
      base_velocity = [0.0, 0.0, 0.0]
    objects = []
    for i, (x, y) in enumerate(positions):
      objects.append({
        "id": f"{category}-{i}",
        "category": category,
        "translation": [float(x), float(y), 0.0],
        "velocity": list(base_velocity),
      })
    return objects
  return _make
