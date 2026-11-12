# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations
from django.db.models import Q


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
    ('manager', '0012_merge_geospatial_glb_fields_and_main'),
  ]

  operations = [
    migrations.RunPython(
      clear_glb_trs_matrix_migration,
      reverse_clear_glb_trs_matrix,
    ),
  ]
