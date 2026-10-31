# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-method scene maps: one current mesh and one artifact zip per method, plus the default pointer."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

import manager.models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0006_osm_roi_support'),
  ]

  operations = [
      migrations.AddField(
          model_name='scene',
          name='map_contributor',
          field=models.CharField(
              blank=True, default='', max_length=200,
              verbose_name='Scene map last contributor'),
      ),
      migrations.CreateModel(
          name='SceneSourceMap',
          fields=[
              ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
              ('file', models.FileField(blank=True, upload_to=manager.models.source_map_upload_to)),
              ('thumbnail', models.ImageField(
                  blank=True, null=True, upload_to=manager.models.source_map_thumbnail_upload_to)),
              ('sha256', models.CharField(max_length=64)),
              ('method', models.CharField(default='user', max_length=32)),
              ('contributor', models.CharField(blank=True, default='', max_length=200)),
              ('created', models.DateTimeField(auto_now_add=True)),
              ('transform', models.JSONField(default=dict)),
              ('scene', models.ForeignKey(
                  on_delete=django.db.models.deletion.CASCADE,
                  related_name='source_maps', to='manager.scene')),
          ],
      ),
      migrations.CreateModel(
          name='SceneMappingArtifact',
          fields=[
              ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
              ('method', models.CharField(max_length=32)),
              ('bundle', models.FileField(upload_to=manager.models.mapping_artifact_upload_to)),
              ('sha256', models.CharField(max_length=64)),
              ('size', models.PositiveBigIntegerField()),
              ('fiducials', models.JSONField(default=list)),
              ('manifest', models.JSONField(blank=True, default=dict)),
              ('created', models.DateTimeField(auto_now_add=True)),
              ('contributor', models.CharField(blank=True, default='', max_length=200)),
              ('scene', models.ForeignKey(
                  on_delete=django.db.models.deletion.CASCADE,
                  related_name='mapping_artifacts', to='manager.scene')),
          ],
      ),
      migrations.AddConstraint(
          model_name='scenemappingartifact',
          constraint=models.UniqueConstraint(
              fields=('scene', 'method'), name='unique_mapping_artifact_per_method'),
      ),
      migrations.AddConstraint(
          model_name='scenesourcemap',
          constraint=models.UniqueConstraint(
              fields=('scene', 'method'), name='unique_source_map_per_method'),
      ),
      migrations.AddField(
          model_name='scene',
          name='default_source_map',
          field=models.ForeignKey(
              blank=True, editable=False, null=True,
              on_delete=django.db.models.deletion.SET_NULL,
              related_name='+', to='manager.scenesourcemap'),
      ),
  ]
