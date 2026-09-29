# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0005_default_asset3d_objects'),
      ('manager', '0002_add_mapping_bundle'),
  ]

  operations = [
      migrations.AddField(
          model_name='scene',
          name='map_contributor',
          field=models.CharField(
              blank=True, default='', max_length=200,
              verbose_name='Scene map last contributor'),
      ),
  ]
