# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Camera pose provenance: pose_locked and calibration_origin."""

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0010_per_method_scene_maps'),
  ]

  operations = [
    # Existing calibrated deployments stay locked so upgrade does not start
    # accepting observation extrinsics on previously fixed cameras.
    migrations.AddField(
      model_name='cam',
      name='pose_locked',
      field=models.BooleanField(default=True, verbose_name='Pose locked'),
    ),
    # New cameras default unlocked until calibrated; calibrate UI defaults locked.
    migrations.AlterField(
      model_name='cam',
      name='pose_locked',
      field=models.BooleanField(default=False, verbose_name='Pose locked'),
    ),
    migrations.AddField(
      model_name='cam',
      name='calibration_origin',
      field=models.CharField(
        blank=True, default='manager.rest', max_length=64,
        verbose_name='Calibration origin'),
    ),
  ]
