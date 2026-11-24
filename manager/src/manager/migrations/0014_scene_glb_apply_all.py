# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


def set_glb_apply_all(apps, schema_editor):
  """Set the Apply All GLBs flag of existing geospatial scenes from their GLB state.

  The flag is True only for a scene that has the GLB applied (use_glb_map) and whose layers
  are all enabled, which is the rule glb_state.sync_apply_all keeps. Other geospatial scenes
  get False. Scenes of other map types have no switch and keep the field default.
  """
  Scene = apps.get_model('manager', 'Scene')
  geospatial = Scene.objects.filter(map_type='geospatial_map')
  geospatial.update(glb_apply_all=False)
  all_enabled = geospatial.filter(use_glb_map=True, glb_layers__isnull=False).exclude(
    glb_layers__enabled=False).values('pk')
  geospatial.filter(pk__in=all_enabled).update(glb_apply_all=True)


def keep_glb_apply_all(apps, schema_editor):
  """Noop reverse: the column is dropped with the field."""
  pass


class Migration(migrations.Migration):

  # Merges the two 0013 leaves: the DLSPS pipeline integration and the GLB layers.
  dependencies = [
    ('manager', '0013_dlsps_pipeline_integration'),
    ('manager', '0013_geospatial_glb_layers'),
  ]

  operations = [
    migrations.AddField(
      model_name='scene',
      name='glb_apply_all',
      field=models.BooleanField(
        default=True, editable=False,
        help_text='Apply All GLBs switch on the scene page: True when the scene has GLB layers and all are enabled',
      ),
    ),
    migrations.RunPython(set_glb_apply_all, keep_glb_apply_all),
  ]
