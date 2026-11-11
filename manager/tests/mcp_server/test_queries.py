# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Inventory query policy without native geometry or database dependencies."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from thin_mcp import ToolExecutionError

from mcp_server import queries
from mcp_server.schemas import (
  CameraSummary, ListArguments, SceneArguments, SceneListArguments, SceneSummary,
)


def test_pagination_selects_only_contract_fields():
  queryset = MagicMock()
  rows = [{'sensor_id': str(i), 'name': f'Camera {i}', 'scene_id': None, 'pose_locked': False}
          for i in range(3)]
  queryset.values.return_value.__getitem__.return_value = rows
  result = queries.inventory_page(queryset, ListArguments(limit=2, offset=10), CameraSummary)
  assert len(result.items) == 2
  assert result.next_offset == 12
  queryset.values.assert_called_once_with('sensor_id', 'name', 'scene_id', 'pose_locked')
  queryset.values.return_value.__getitem__.assert_called_once_with(slice(10, 13))


def test_empty_page_has_no_next_offset():
  queryset = MagicMock()
  queryset.values.return_value.__getitem__.return_value = []
  result = queries.inventory_page(queryset, ListArguments(), SceneSummary)
  assert result.items == []
  assert result.next_offset is None


@pytest.mark.parametrize('function,model_name,order', [
  (queries.list_cameras, 'Cam', 'sensor_id'), (queries.list_regions, 'Region', 'uuid'),
])
def test_scene_filter_and_stable_order(monkeypatch, function, model_name, order):
  model = MagicMock()
  queryset = model.objects.order_by.return_value.filter.return_value
  queryset.values.return_value.__getitem__.return_value = []
  monkeypatch.setitem(sys.modules, 'manager.models', SimpleNamespace(**{model_name: model}))
  scene_id = uuid4()
  assert function(SceneListArguments(scene_id=scene_id)).items == []
  model.objects.order_by.assert_called_once_with(order)
  model.objects.order_by.return_value.filter.assert_called_once_with(scene_id=scene_id)


def test_missing_scene(monkeypatch):
  scene = MagicMock()
  scene.objects.filter.return_value.values.return_value.first.return_value = None
  monkeypatch.setitem(sys.modules, 'manager.models', SimpleNamespace(Scene=scene))
  scene_id = uuid4()
  with pytest.raises(ToolExecutionError, match='Scene not found'):
    queries.get_scene(SceneArguments(scene_id=scene_id))
  scene.objects.filter.assert_called_once_with(pk=scene_id)
