# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0005_add_osm_ways_cache_to_scene'),
  ]

  operations = [
    migrations.AddField(
      model_name='scene',
      name='osm_ways_cache_bbox',
      field=models.JSONField(
        blank=True,
        null=True,
        default=None,
        editable=False,
        help_text="Bounding box [south, west, north, east] used to fetch osm_ways_cache; cleared on map edit",
        verbose_name='Cached bounding box for OSM ways query',
      ),
    ),
  ]
