# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import manager.validators
from django.db import migrations, models
from django.db.models import Q
from django.core.files import File


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


def clear_glb_trs_matrix(Scene):
  """Clear the cached trs_matrix of geospatial scenes that use a GLB map.

  apply, unapply and move keep trs_matrix as it was, so the cached value can
  predate the current GLB pose. Clearing it makes the controller recompute it
  from the stored pose and map corners. The controller pushes the new value
  back on its next connect (updateTRSMatrix). Until then, OSM ROI calls for
  these scenes report that the scene is not ready.
  """
  glb_scenes = Scene.objects.filter(map_type='geospatial_map').filter(
    Q(use_glb_map=True) | Q(map__iendswith='.glb'))
  return glb_scenes.update(trs_matrix=None)


def clear_glb_trs_matrix_migration(apps, schema_editor):
  Scene = apps.get_model('manager', 'Scene')
  clear_glb_trs_matrix(Scene)


def reverse_clear_glb_trs_matrix(apps, schema_editor):
  """Noop reverse: the cleared cache is rebuilt by the controller."""
  pass


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0011_cam_pose_provenance'),
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
    migrations.AlterField(
      model_name='scene',
      name='map_corners_lla',
      field=models.JSONField(blank=True, default=None, help_text="Provide the array of four map corners geospatial coordinates (lat, long, alt).\nRequired only if 'Output geospatial coordinates' is set to `Yes`.\nExpected order: starting from the bottom-left corner, either counterclockwise or clockwise.\nExpected JSON format: '[ [lat1, lon1, alt1], [lat2, lon2, alt2], [lat3, lon3, alt3], [lat4, lon4, alt4] ]'", null=True, validators=[manager.validators.validate_map_corners_lla], verbose_name='Geospatial coordinates of the four map corners in JSON format'),
    ),
    # Initialise the GLB fields from existing GLB maps, then clear the trs_matrix that those
    # scenes (and any already using a GLB) cached before the new pose was stored.
    migrations.RunPython(migrate_existing_glb_maps, reverse_glb_migration),
    migrations.RunPython(clear_glb_trs_matrix_migration, reverse_clear_glb_trs_matrix),
  ]
