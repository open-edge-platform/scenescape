# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0001_initial'),
  ]

  operations = [
      migrations.AddField(
          model_name='childscene',
          name='transform_source',
          field=models.CharField(
              blank=True,
              choices=[('manual', 'Manual'), ('geospatial', 'Geospatial')],
              default='manual',
              help_text="How the child pose was obtained. Geospatial links are recomputed when either scene's map corners or scale change.",
              max_length=16,
          ),
      ),
  ]
