# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0003_add_cached_geometries_to_childscene'),
  ]

  operations = [
    migrations.AddField(
      model_name='scene',
      name='map_max_x',
      field=models.FloatField(
        blank=True,
        default=None,
        help_text='Maximum scene map extent along X in meters (origin at map corner).',
        null=True,
        verbose_name='Map max X (meters)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='map_max_y',
      field=models.FloatField(
        blank=True,
        default=None,
        help_text='Maximum scene map extent along Y in meters (origin at map corner).',
        null=True,
        verbose_name='Map max Y (meters)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='map_max_z',
      field=models.FloatField(
        blank=True,
        default=None,
        help_text='Maximum scene map extent along Z in meters. For 2D maps use -1.0 to indicate unbounded height.',
        null=True,
        verbose_name='Map max Z (meters)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='track_within_bounds',
      field=models.BooleanField(
        blank=True,
        choices=[(True, 'Yes'), (False, 'No')],
        default=False,
        help_text='When enabled, only track objects whose location is inside the map bounds (volume of interest). Disabled by default.',
        verbose_name='Track only within map bounds',
      ),
    ),
  ]
