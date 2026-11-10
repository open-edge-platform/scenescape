# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models
from django.core.files import File
import os


def migrate_existing_glb_maps(apps, schema_editor):
  """For existing geospatial scenes with GLB maps, initialize the new fields."""
  Scene = apps.get_model('manager', 'Scene')
  from scene_common.earth_lla import footprintAnchorFromCornersLLA

  for scene in Scene.objects.filter(map_type='geospatial_map'):
    if not scene.map or not scene.map.name.lower().endswith('.glb'):
      continue
    if scene.map_corners_lla and not scene.glb_anchor:
      try:
        lat, lng, heading, w, h = footprintAnchorFromCornersLLA(scene.map_corners_lla)
        # Known bug: the legacy X rotation is not stored, so move and reapply use ALIGN_ROTATION_X.
        # Supposed to be resolved by ITEP-97904 PR.
        scene.glb_anchor = {
          'lat': float(lat),
          'lng': float(lng),
          'heading_deg': float(heading),
          'footprint_m': {'width': float(w), 'height': float(h)},
        }
        # Copy the current map to glb_map
        if scene.map.name and scene.map.storage.exists(scene.map.name):
          glb_map_name = f'{scene.name}.glb'
          with scene.map.storage.open(scene.map.name, 'rb') as f:
            scene.glb_map.save(glb_map_name, File(f), save=False)
        scene.use_glb_map = True
        scene.base_map_corners_lla = scene.map_corners_lla
        scene.save(update_fields=['glb_map', 'glb_anchor', 'use_glb_map', 'base_map_corners_lla'])
      except Exception as e:
        print(f"Failed to migrate scene {scene.name}: {e}")


def reverse_glb_migration(apps, schema_editor):
  """Noop reverse: leave glb_map, glb_anchor, use_glb_map, base_* as they are."""
  pass


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0006_osm_roi_support'),
  ]

  operations = [
    migrations.AddField(
      model_name='scene',
      name='glb_map',
      field=models.FileField(
        null=True,
        blank=True,
        editable=False,
        upload_to='glb_maps/',
        help_text='Stored GLB file for geospatial alignment (unposed)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='glb_anchor',
      field=models.JSONField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        help_text='Geographic centre and heading of the GLB footprint: {lat, lng, heading_deg, footprint_m}',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='use_glb_map',
      field=models.BooleanField(
        default=False,
        editable=False,
        help_text='Whether the GLB is currently applied (True) or the snapshot is active (False)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='base_map',
      field=models.FileField(
        null=True,
        blank=True,
        editable=False,
        upload_to='base_maps/',
        help_text='Snapshot image saved when GLB is applied',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='base_scale',
      field=models.FloatField(
        null=True,
        blank=True,
        editable=False,
        help_text='Snapshot scale (px/m) saved when GLB is applied',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='base_map_corners_lla',
      field=models.JSONField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        help_text='Snapshot map corners (invariant frame) saved when GLB is applied',
      ),
    ),
    migrations.RunPython(migrate_existing_glb_maps, reverse_glb_migration),
  ]
