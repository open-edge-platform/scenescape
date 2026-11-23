# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""GlbLayer schema: backfill from migration 0013, unique order per scene, shared file safety."""

import importlib
import io
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from manager import glb_state
from manager.glb_staging import GlbAlignmentError
from manager.models import GlbLayer, Scene, delete_unreferenced_mapping_file
from tests.utils.geo_footprint import localFootprintCornersLLA

migration = importlib.import_module('manager.migrations.0013_geospatial_glb_layers')
TEST_GLB_FILE = Path(__file__).resolve().parent.parent / 'mesh_util' / 'test_data' / 'scene.glb'

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


@pytest.mark.django_db
def test_backfill_normalises_provider_order_corners(settings, tmp_path):
  """Provider-ordered (SW, NW, NE, SE) corners give a north-up anchor with unswapped width and height."""
  settings.MEDIA_ROOT = str(tmp_path)
  ccw = localFootprintCornersLLA(
    center_lat=37.38, center_lng=-121.96, heading_deg=0.0,
    width_m=300.0, height_m=200.0,
  )
  provider_order = ccw[[0, 3, 2, 1]].tolist()  # SW, NW, NE, SE
  shutil.copy(TEST_GLB_FILE, tmp_path / 'legacy_migrate.glb')

  scene = Scene.objects.create(
    name='legacy_migrate', map_type='geospatial_map', map_center_lat=37.38,
    map_center_lng=-121.96, output_lla=True,
  )
  scene.map = 'legacy_migrate.glb'
  scene.map_corners_lla = provider_order
  scene.save()

  with patch.object(Scene, 'saveThumbnail'), patch('manager.models.sendUpdateCommand'):
    migration.migrate_existing_glb_maps(apps, None)
  scene.refresh_from_db()

  layer = scene.glb_layers.get()
  heading = layer.anchor['heading_deg']
  assert min(heading, 360.0 - heading) < 1e-6
  assert layer.anchor['footprint_m']['width'] == pytest.approx(300.0, rel=1e-6)
  assert layer.anchor['footprint_m']['height'] == pytest.approx(200.0, rel=1e-6)
  assert scene.use_glb_map is True


@pytest.mark.parametrize('error', [ValidationError('bad uuid'), ValueError('bad uuid')])
def test_get_layer_maps_malformed_id_to_404(error):
  """A layer id the ORM cannot parse is a 404, not a 500."""
  scene = MagicMock()
  scene.glb_layers.filter.side_effect = error

  with pytest.raises(GlbAlignmentError) as exc:
    glb_state.get_layer(scene, 'not-a-uuid')

  assert exc.value.status == 404
