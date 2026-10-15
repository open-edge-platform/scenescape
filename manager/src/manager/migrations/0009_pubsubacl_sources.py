# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0008_pubsubacl_scenes"),
  ]

  operations = [
    migrations.AddField(
      model_name="pubsubacl",
      name="sources",
      field=models.JSONField(blank=True, default=list),
    ),
  ]
