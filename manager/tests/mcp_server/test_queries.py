# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Inventory query policy without native geometry or database dependencies."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from thin_mcp import ToolExecutionError

from mcp_server import queries
from mcp_server.schemas import ListArguments, SceneArguments, SceneSummary


def test_pagination_selects_only_contract_fields():
  queryset = MagicMock()
  rows = [{'id': uuid4(), 'name': f'Scene {i}', 'map_type': None, 'scale': None, 'use_tracker': True}
          for i in range(5)]
  queryset.values.return_value = rows
  result = queries.inventory_page(queryset, ListArguments(limit=2, page=2), SceneSummary)
  assert [item.id for item in result.items] == [row['id'] for row in rows[2:4]]
  assert result.next_page == 3
  queryset.values.assert_called_once_with('id', 'name', 'map_type', 'scale', 'use_tracker')


def test_empty_inventory_and_out_of_range_page():
  queryset = MagicMock()
  queryset.values.return_value = []
  result = queries.inventory_page(queryset, ListArguments(), SceneSummary)
  assert result.items == []
  assert result.next_page is None
  with pytest.raises(ToolExecutionError, match='Page does not exist'):
    queries.inventory_page(queryset, ListArguments(page=2), SceneSummary)


def test_list_scenes_uses_stable_order(monkeypatch):
  scene = MagicMock()
  scene.objects.order_by.return_value.values.return_value = []
  monkeypatch.setattr(queries, 'Scene', scene)
  assert queries.list_scenes(ListArguments()).items == []
  scene.objects.order_by.assert_called_once_with('id')


def test_missing_scene(monkeypatch):
  scene = MagicMock()
  scene.objects.filter.return_value.values.return_value.first.return_value = None
  monkeypatch.setattr(queries, 'Scene', scene)
  scene_id = uuid4()
  with pytest.raises(ToolExecutionError, match='Scene not found'):
    queries.get_scene(SceneArguments(scene_id=scene_id))
  scene.objects.filter.assert_called_once_with(pk=scene_id)
