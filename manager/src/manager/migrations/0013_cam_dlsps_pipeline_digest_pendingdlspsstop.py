# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0012_merge_pipeline_and_camera_pose'),
  ]

  operations = [
    migrations.AddField(
      model_name='cam',
      name='dlsps_pipeline_digest',
      field=models.CharField(blank=True, editable=False, max_length=64, null=True),
    ),
    migrations.AddField(
      model_name='cam',
      name='dlsps_start_uncertain',
      field=models.BooleanField(default=False, editable=False),
    ),
    migrations.CreateModel(
      name='PendingDLSPSStop',
      fields=[
        ('id', models.AutoField(auto_created=True, primary_key=True,
                               serialize=False, verbose_name='ID')),
        ('instance_id', models.UUIDField(blank=True, null=True, unique=True)),
        ('pipeline_digest', models.CharField(blank=True, max_length=64, null=True)),
        ('attempts', models.PositiveIntegerField(default=0)),
        ('last_error', models.TextField(blank=True, default='')),
        ('created_at', models.DateTimeField(auto_now_add=True)),
      ],
    ),
  ]
