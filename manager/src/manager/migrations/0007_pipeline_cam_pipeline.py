# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0006_osm_roi_support'),
  ]

  operations = [
    migrations.CreateModel(
      name='Pipeline',
      fields=[
        ('id', models.AutoField(auto_created=True, primary_key=True,
                               serialize=False, verbose_name='ID')),
        ('name', models.CharField(max_length=200, unique=True)),
        ('pipeline', models.TextField(verbose_name='Pipeline string')),
        ('vippet_pipeline_id', models.TextField(blank=True, editable=False, null=True)),
      ],
      options={'ordering': ['name']},
    ),
    migrations.AddField(
      model_name='cam',
      name='pipeline',
      field=models.ForeignKey(
        blank=True,
        help_text='Selecting a pipeline starts it on DL Streamer Pipeline Server for this camera; changing or clearing it stops the running instance.',
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name='cameras',
        to='manager.pipeline',
      ),
    ),
    migrations.AddField(
      model_name='cam',
      name='dlsps_instance_id',
      field=models.UUIDField(blank=True, editable=False, null=True),
    ),
    migrations.AddConstraint(
      model_name='cam',
      constraint=models.UniqueConstraint(fields=('pipeline',), name='unique_camera_pipeline'),
    ),
  ]
