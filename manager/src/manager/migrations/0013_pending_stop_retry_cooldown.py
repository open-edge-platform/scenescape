# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0012_dlsps_pipeline_integration'),
  ]

  operations = [
    migrations.AddField(
      model_name='pendingdlspsstop',
      name='next_retry_at',
      field=models.DateTimeField(blank=True, null=True),
    ),
  ]
