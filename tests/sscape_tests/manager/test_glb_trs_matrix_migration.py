# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for migration 0013 (clear cached trs_matrix of GLB scenes).

No DB needed: the Scene model is replaced by a mock that records the
queryset calls.
"""

import importlib
from unittest.mock import MagicMock

migration = importlib.import_module('manager.migrations.0013_clear_glb_trs_matrix')


def _fake_scene_model():
  queryset = MagicMock(name='queryset')
  queryset.update.return_value = 3
  scene_model = MagicMock(name='Scene')
  scene_model.objects.filter.return_value = queryset
  queryset.filter.return_value = queryset
  return scene_model, queryset


def test_clears_trs_matrix_on_geospatial_scenes():
  scene_model, queryset = _fake_scene_model()

  updated = migration.clear_glb_trs_matrix(scene_model)

  scene_model.objects.filter.assert_called_once_with(map_type='geospatial_map')
  queryset.update.assert_called_once_with(trs_matrix=None)
  assert updated == 3


def test_filter_selects_applied_glb_or_glb_map_only():
  scene_model, queryset = _fake_scene_model()

  migration.clear_glb_trs_matrix(scene_model)

  (q_filter,), _ = queryset.filter.call_args
  rendered = str(q_filter)
  assert 'use_glb_map' in rendered
  assert 'map__iendswith' in rendered
  assert '.glb' in rendered


def test_forward_migration_passes_historical_model():
  apps = MagicMock(name='apps')
  scene_model, _ = _fake_scene_model()
  apps.get_model.return_value = scene_model

  migration.clear_glb_trs_matrix_migration(apps, None)

  apps.get_model.assert_called_once_with('manager', 'Scene')
  scene_model.objects.filter.assert_called_once_with(map_type='geospatial_map')


def test_reverse_is_noop():
  apps = MagicMock(name='apps')
  migration.reverse_clear_glb_trs_matrix(apps, None)
  apps.get_model.assert_not_called()


def test_migration_depends_on_current_leaf():
  assert ('manager', '0012_merge_geospatial_glb_fields_and_main') in (
    migration.Migration.dependencies)
