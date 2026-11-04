# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0008_cam_pose_locked'),
  ]

  operations = [
    migrations.AddField(
      model_name='cam',
      name='calibration_origin',
      field=models.CharField(
        blank=True, default='manager.rest', max_length=64,
        verbose_name='Calibration origin'),
    ),
  ]
