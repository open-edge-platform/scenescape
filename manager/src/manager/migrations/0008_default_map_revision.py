# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""All scene GLBs become method-tagged revisions behind one default pointer."""

import django.db.models.deletion
import manager.models
from django.db import migrations, models


def _scene_transform(scene):
  return {
    "translation": [scene.translation_x or 0.0, scene.translation_y or 0.0,
                    scene.translation_z or 0.0],
    "rotation": [scene.rotation_x or 0.0, scene.rotation_y or 0.0,
                 scene.rotation_z or 0.0],
    "scale": [scene.scale_x if scene.scale_x is not None else 1.0,
              scene.scale_y if scene.scale_y is not None else 1.0,
              scene.scale_z if scene.scale_z is not None else 1.0],
  }


def forwards(apps, schema_editor):
  Scene = apps.get_model("manager", "Scene")
  SceneMapRevision = apps.get_model("manager", "SceneMapRevision")
  SceneMappingArtifact = apps.get_model("manager", "SceneMappingArtifact")

  # Revisions uploaded with a method's artifact take that method's name;
  # everything else was a direct GLB upload.
  method_by_revision = {}
  for artifact in SceneMappingArtifact.objects.exclude(map_revision=None):
    method_by_revision.setdefault(artifact.map_revision_id, artifact.method)
  for revision in SceneMapRevision.objects.all():
    method = method_by_revision.get(revision.id)
    if method is None and revision.method in ("", "upload"):
      method = "user"
    if method and method != revision.method:
      revision.method = method
      revision.save(update_fields=["method"])

  for scene in Scene.objects.all():
    head = SceneMapRevision.objects.filter(scene=scene, head=True).first()
    if head is None and scene.map and scene.map.name.lower().endswith(".glb"):
      head = SceneMapRevision(
        scene=scene, sha256="", method="user",
        contributor=scene.map_contributor or "",
        transform=_scene_transform(scene))
      head.file.name = scene.map.name
      head.save()
    if head is not None:
      Scene.objects.filter(pk=scene.pk).update(default_map_revision=head)


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0007_per_method_map_storage'),
  ]

  operations = [
      migrations.AddField(
          model_name='scene',
          name='default_map_revision',
          field=models.ForeignKey(
              blank=True, editable=False, null=True,
              on_delete=django.db.models.deletion.SET_NULL,
              related_name='+', to='manager.scenemaprevision'),
      ),
      migrations.RenameField(
          model_name='scenemaprevision', old_name='source', new_name='method'),
      migrations.AlterField(
          model_name='scenemaprevision',
          name='method',
          field=models.CharField(default='user', max_length=32),
      ),
      migrations.AddField(
          model_name='scenemaprevision',
          name='thumbnail',
          field=models.ImageField(
              blank=True, null=True,
              upload_to=manager.models.map_revision_thumbnail_upload_to),
      ),
      migrations.AddField(
          model_name='scenemappingartifact',
          name='manifest',
          field=models.JSONField(blank=True, default=dict),
      ),
      migrations.RunPython(forwards, migrations.RunPython.noop),
      migrations.RemoveConstraint(
          model_name='scenemaprevision', name='unique_head_map_revision'),
      migrations.RemoveField(model_name='scenemaprevision', name='head'),
  ]
