# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GlbLayer schema: backfill from migration 0012, unique order per scene, shared file safety."""

import importlib
import io
from unittest.mock import MagicMock

import pytest
from django.db import IntegrityError, transaction

from manager.models import GlbLayer, Scene, delete_unreferenced_mapping_file
from scene_common.earth_lla import localFootprintCornersLLA

migration = importlib.import_module('manager.migrations.0012_geospatial_glb_fields')

CORNERS = localFootprintCornersLLA(
  center_lat=37.38689, center_lng=-121.96411, heading_deg=0.0,
  width_m=100.0, height_m=100.0,
).tolist()


def test_backfill_creates_first_enabled_layer_from_glb_map():
  scene = MagicMock(name='scene', map_type='geospatial_map', map_corners_lla=CORNERS)
  scene.name = 'legacy'
  scene.map.name = 'legacy.glb'
  scene.map.storage.exists.return_value = True
  scene.map.storage.open.return_value.__enter__.return_value = io.BytesIO(b'glb')
  scene_model = MagicMock(name='Scene')
  scene_model.objects.filter.return_value = [scene]
  layer_model = MagicMock(name='GlbLayer')
  layer_model.objects.filter.return_value.exists.return_value = False
  apps = MagicMock(name='apps')
  apps.get_model.side_effect = lambda app, name: {'Scene': scene_model, 'GlbLayer': layer_model}[name]

  migration.migrate_existing_glb_maps(apps, None)

  kwargs = layer_model.call_args.kwargs
  assert kwargs['scene'] is scene
  assert kwargs['order'] == 0
  assert kwargs['enabled'] is True
  assert set(kwargs['anchor']) == {'lat', 'lng', 'heading_deg', 'footprint_m'}
  layer_model.return_value.file.save.assert_called_once()
  assert scene.use_glb_map is True
  assert scene.base_map_corners_lla == CORNERS


def test_backfill_skips_scene_that_already_has_a_layer():
  scene = MagicMock(name='scene', map_type='geospatial_map', map_corners_lla=CORNERS)
  scene.map.name = 'legacy.glb'
  scene_model = MagicMock(name='Scene')
  scene_model.objects.filter.return_value = [scene]
  layer_model = MagicMock(name='GlbLayer')
  layer_model.objects.filter.return_value.exists.return_value = True
  apps = MagicMock(name='apps')
  apps.get_model.side_effect = lambda app, name: {'Scene': scene_model, 'GlbLayer': layer_model}[name]

  migration.migrate_existing_glb_maps(apps, None)

  layer_model.assert_not_called()


@pytest.mark.django_db
def test_layer_order_is_unique_per_scene():
  scene = Scene.objects.create(name='layers', map_type='geospatial_map', output_lla=True)
  GlbLayer.objects.create(scene=scene, order=0, file='glb_maps/a.glb')
  with pytest.raises(IntegrityError), transaction.atomic():
    GlbLayer.objects.create(scene=scene, order=0, file='glb_maps/b.glb')


@pytest.mark.django_db
def test_file_referenced_by_layer_is_kept():
  scene = Scene.objects.create(name='kept', map_type='geospatial_map', output_lla=True)
  GlbLayer.objects.create(scene=scene, order=0, file='glb_maps/kept.glb')
  storage = MagicMock(name='storage')
  storage.exists.return_value = True

  delete_unreferenced_mapping_file(storage, 'glb_maps/kept.glb', 'default')

  storage.delete.assert_not_called()
