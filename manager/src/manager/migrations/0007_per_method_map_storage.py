# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import django.db.models.deletion
import manager.models
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0006_scene_map_contributor'),
  ]

  operations = [
      migrations.RemoveField(model_name='scene', name='mapping_bundle'),
      migrations.RemoveField(model_name='scene', name='mapping_bundle_updated'),
      migrations.RemoveField(model_name='scene', name='mapping_bundle_contributor'),
      migrations.RemoveField(model_name='scene', name='arkit_mapping_bundle'),
      migrations.RemoveField(model_name='scene', name='arkit_mapping_bundle_updated'),
      migrations.RemoveField(model_name='scene', name='arkit_mapping_bundle_contributor'),
      migrations.RemoveField(model_name='scene', name='map_backend'),
      migrations.CreateModel(
          name='SceneMapRevision',
          fields=[
              ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
              ('file', models.FileField(blank=True, upload_to=manager.models.map_revision_upload_to)),
              ('sha256', models.CharField(max_length=64)),
              ('source', models.CharField(max_length=32)),
              ('contributor', models.CharField(blank=True, default='', max_length=200)),
              ('created', models.DateTimeField(auto_now_add=True)),
              ('transform', models.JSONField(default=dict)),
              ('head', models.BooleanField(default=False)),
              ('scene', models.ForeignKey(
                  on_delete=django.db.models.deletion.CASCADE,
                  related_name='map_revisions', to='manager.scene')),
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
              ('created', models.DateTimeField(auto_now_add=True)),
              ('contributor', models.CharField(blank=True, default='', max_length=200)),
              ('head', models.BooleanField(default=False)),
              ('map_revision', models.ForeignKey(
                  blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                  related_name='artifacts', to='manager.scenemaprevision')),
              ('scene', models.ForeignKey(
                  on_delete=django.db.models.deletion.CASCADE,
                  related_name='mapping_artifacts', to='manager.scene')),
          ],
      ),
      migrations.AddConstraint(
          model_name='scenemaprevision',
          constraint=models.UniqueConstraint(
              condition=models.Q(('head', True)),
              fields=('scene',),
              name='unique_head_map_revision'),
      ),
      migrations.AddConstraint(
          model_name='scenemappingartifact',
          constraint=models.UniqueConstraint(
              condition=models.Q(('head', True)),
              fields=('scene', 'method'),
              name='unique_head_mapping_artifact'),
      ),
  ]
