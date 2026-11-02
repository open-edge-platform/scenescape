# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0007_per_method_scene_maps'),
  ]

  operations = [
    # Backfill existing cameras as configured so upgrade does not start
    # accepting observation extrinsics on previously fixed calibrations.
    migrations.AddField(
      model_name='cam',
      name='pose_policy',
      field=models.CharField(
        choices=[('configured', 'Configured'), ('observation', 'Observation-driven')],
        default='configured', max_length=16, verbose_name='Pose policy',
      ),
    ),
    # New registrations default to observation for handheld / live pose.
    migrations.AlterField(
      model_name='cam',
      name='pose_policy',
      field=models.CharField(
        choices=[('configured', 'Configured'), ('observation', 'Observation-driven')],
        default='observation', max_length=16, verbose_name='Pose policy',
      ),
    ),
  ]
