# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0007_per_method_scene_maps'),
  ]

  operations = [
    migrations.AddField(
      model_name='cam',
      name='pose_policy',
      field=models.CharField(
        choices=[('configured', 'Configured'), ('observation', 'Observation-driven')],
        default='observation', max_length=16, verbose_name='Pose policy',
      ),
    ),
  ]
