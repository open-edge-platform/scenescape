# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0005_default_asset3d_objects'),
  ]

  operations = [
    migrations.CreateModel(
      name='Pipeline',
      fields=[
        ('id', models.AutoField(auto_created=True, primary_key=True,
                               serialize=False, verbose_name='ID')),
        ('name', models.CharField(max_length=200, unique=True)),
        ('pipeline', models.TextField(verbose_name='Pipeline string')),
      ],
      options={'ordering': ['name']},
    ),
    migrations.AddField(
      model_name='cam',
      name='pipeline',
      field=models.ForeignKey(
        blank=True,
        help_text='Stored association only. Selecting a pipeline does not change video processing.',
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name='cameras',
        to='manager.pipeline',
      ),
    ),
  ]
