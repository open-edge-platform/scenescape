# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0011_cam_pose_provenance'),
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
    migrations.AddField(
      model_name='cam',
      name='dlsps_pipeline_digest',
      field=models.CharField(blank=True, editable=False, max_length=64, null=True),
    ),
    migrations.AddField(
      model_name='cam',
      name='dlsps_launch_id',
      field=models.UUIDField(blank=True, editable=False, null=True),
    ),
    migrations.AddConstraint(
      model_name='cam',
      constraint=models.UniqueConstraint(fields=('pipeline',), name='unique_camera_pipeline'),
    ),
    migrations.CreateModel(
      name='PendingDLSPSStop',
      fields=[
        ('id', models.AutoField(auto_created=True, primary_key=True,
                               serialize=False, verbose_name='ID')),
        ('instance_id', models.UUIDField(blank=True, null=True, unique=True)),
        ('launch_id', models.UUIDField(blank=True, null=True, unique=True)),
        ('attempts', models.PositiveIntegerField(default=0)),
        ('last_error', models.TextField(blank=True, default='')),
        ('created_at', models.DateTimeField(auto_now_add=True)),
      ],
    ),
  ]
