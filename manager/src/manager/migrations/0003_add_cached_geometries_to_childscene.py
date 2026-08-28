# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0002_region_visible_singletonsensor_visible_and_more'),

  ]

  operations = [
    migrations.AddField(
      model_name="childscene",
      name="cached_tripwires",
      field=models.JSONField(blank=True, default=list, verbose_name="Cached remote tripwires"),
    ),
    migrations.AddField(
      model_name="childscene",
      name="cached_rois",
      field=models.JSONField(blank=True, default=list, verbose_name="Cached remote rois"),
    ),
  ]
