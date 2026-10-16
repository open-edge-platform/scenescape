# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0007_add_ptz_calibration_to_cam"),
  ]

  operations = [
    migrations.AddField(
      model_name="pubsubacl",
      name="scenes",
      field=models.ManyToManyField(blank=True, related_name="pubsub_acls", to="manager.scene"),
    ),
    migrations.AddField(
      model_name="pubsubacl",
      name="all_scenes",
      field=models.BooleanField(default=False),
    ),
  ]
