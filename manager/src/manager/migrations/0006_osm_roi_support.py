# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0005_default_asset3d_objects'),
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
    migrations.AddField(
      model_name='scene',
      name='osm_ways_cache_bbox',
      field=models.JSONField(
        blank=True,
        null=True,
        default=None,
        editable=False,
        help_text="Bounding box [south, west, north, east] used to fetch osm_ways_cache; "
                  "stale once it no longer matches the scene's map corners",
        verbose_name='Cached bounding box for OSM ways query',
      ),
    ),
    migrations.AddField(
      model_name='region',
      name='roi_type',
      field=models.CharField(
        max_length=150,
        default='',
        blank=True,
        help_text='Type or category of the Region of Interest',
      ),
    ),
  ]
