# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Generated migration for adding roi_type field to Region

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0007_merge_asset3d_objects_and_osm_ways_cache'),
  ]

  operations = [
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
