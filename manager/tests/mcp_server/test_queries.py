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
  ListArguments, SceneArguments, SceneSummary,
)


def test_pagination_selects_only_contract_fields():
  queryset = MagicMock()
  rows = [{'id': uuid4(), 'name': f'Scene {i}', 'map_type': None, 'scale': None, 'use_tracker': True}
          for i in range(3)]
  queryset.values.return_value.__getitem__.return_value = rows
  result = queries.inventory_page(queryset, ListArguments(limit=2, offset=10), SceneSummary)
  assert len(result.items) == 2
  assert result.next_offset == 12
  queryset.values.assert_called_once_with('id', 'name', 'map_type', 'scale', 'use_tracker')
  queryset.values.return_value.__getitem__.assert_called_once_with(slice(10, 13))


def test_empty_page_has_no_next_offset():
  queryset = MagicMock()
  queryset.values.return_value.__getitem__.return_value = []
  result = queries.inventory_page(queryset, ListArguments(), SceneSummary)
  assert result.items == []
  assert result.next_offset is None


@pytest.mark.parametrize('offset,limit,row_count,expected', [
  (99975, 25, 26, 100000),
  (99975, 25, 25, None),
  (99976, 25, 26, None),
  (100000, 25, 26, None),
  (99999, 1, 2, 100000),
  (100000, 1, 2, None),
])
def test_pagination_continuation_respects_offset_limit(offset, limit, row_count, expected):
  """Continue at the boundary only when the next request can accept the offset."""
  queryset = MagicMock()
  rows = [{'id': uuid4(), 'name': f'Scene {i}', 'map_type': None, 'scale': None, 'use_tracker': True}
          for i in range(row_count)]
  queryset.values.return_value.__getitem__.return_value = rows
  result = queries.inventory_page(queryset, ListArguments(limit=limit, offset=offset), SceneSummary)
  assert len(result.items) == min(limit, row_count)
  assert result.next_offset == expected
  if result.next_offset is not None:
    assert ListArguments(limit=limit, offset=result.next_offset).offset == expected


def test_list_scenes_uses_stable_order(monkeypatch):
  """Order scene pages by their stable unique identifier."""
  scene = MagicMock()
  scene.objects.order_by.return_value.values.return_value.__getitem__.return_value = []
  monkeypatch.setitem(sys.modules, 'manager.models', SimpleNamespace(Scene=scene))
  assert queries.list_scenes(ListArguments()).items == []
  scene.objects.order_by.assert_called_once_with('id')


def test_missing_scene(monkeypatch):
  scene = MagicMock()
  scene.objects.filter.return_value.values.return_value.first.return_value = None
  monkeypatch.setitem(sys.modules, 'manager.models', SimpleNamespace(Scene=scene))
  scene_id = uuid4()
  with pytest.raises(ToolExecutionError, match='Scene not found'):
    queries.get_scene(SceneArguments(scene_id=scene_id))
  scene.objects.filter.assert_called_once_with(pk=scene_id)
