# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0005_add_arkit_mapping_bundle'),
  ]

  operations = [
      migrations.AddField(
          model_name='scene',
          name='map_backend',
          field=models.CharField(
              blank=True, choices=[
                  ('rtabmap', 'RTAB-Map (Linux)'),
                  ('arkit', 'ARKit (iOS)'),
                  ('unknown', 'Unknown'),
              ],
              default='unknown', max_length=20,
              verbose_name='Scene map last backend'),
      ),
      migrations.AddField(
          model_name='scene',
          name='map_contributor',
          field=models.CharField(
              blank=True, default='', max_length=200,
              verbose_name='Scene map last contributor'),
      ),
  ]
