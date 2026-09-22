# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models

import manager.validators


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0004_add_cached_sensors_to_childscene'),

  ]

  operations = [
    migrations.AlterField(
      model_name="scene",
      name="name",
      field=models.CharField(max_length=200, unique=True, validators=[manager.validators.validate_scene_name]),
    ),
  ]
