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
      name='osm_bbox_south',
      field=models.FloatField(
        blank=True,
        null=True,
        help_text='Southern latitude for OpenStreetMap query bounding box',
        verbose_name='OSM Query Bbox South (latitude)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='osm_bbox_west',
      field=models.FloatField(
        blank=True,
        null=True,
        help_text='Western longitude for OpenStreetMap query bounding box',
        verbose_name='OSM Query Bbox West (longitude)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='osm_bbox_north',
      field=models.FloatField(
        blank=True,
        null=True,
        help_text='Northern latitude for OpenStreetMap query bounding box',
        verbose_name='OSM Query Bbox North (latitude)',
      ),
    ),
    migrations.AddField(
      model_name='scene',
      name='osm_bbox_east',
      field=models.FloatField(
        blank=True,
        null=True,
        help_text='Eastern longitude for OpenStreetMap query bounding box',
        verbose_name='OSM Query Bbox East (longitude)',
      ),
    ),
  ]
