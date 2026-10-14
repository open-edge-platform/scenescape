# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0006_positioning_mqtt_topics"),
  ]

  operations = [
    migrations.AddField(
      model_name="cam",
      name="ptz_calibration",
      field=models.JSONField(blank=True, default=None, null=True),
    ),
  ]