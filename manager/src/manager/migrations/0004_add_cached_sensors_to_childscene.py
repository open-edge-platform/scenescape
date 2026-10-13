# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0003_add_cached_geometries_to_childscene'),

  ]

  operations = [
    migrations.AddField(
      model_name="childscene",
      name="cached_sensors",
      field=models.JSONField(blank=True, default=list, verbose_name="Cached remote sensors"),
    ),
  ]
