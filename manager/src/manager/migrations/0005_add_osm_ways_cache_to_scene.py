# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0004_add_cached_sensors_to_childscene'),
  ]

  operations = [
    migrations.AddField(
      model_name='scene',
      name='osm_ways_cache',
      field=models.JSONField(
        blank=True,
        null=True,
        default=None,
        editable=False,
        help_text="Cached raw OSM way geometries fetched for this scene's map corners bounding box",
        verbose_name='Cached OpenStreetMap way geometries for this scene',
      ),
    ),
  ]
