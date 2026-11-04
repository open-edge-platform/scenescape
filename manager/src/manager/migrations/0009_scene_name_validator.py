# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models

from manager.validators import (
  SCENE_NAME_DB_PATTERN, is_valid_scene_name, sanitize_scene_name, validate_scene_name)


def sanitize_legacy_scene_names(apps, schema_editor):
  Scene = apps.get_model('manager', 'Scene')
  used_names = set(Scene.objects.values_list('name', flat=True))
  for scene in Scene.objects.all():
    if is_valid_scene_name(scene.name):
      continue
    used_names.discard(scene.name)
    new_name = sanitize_scene_name(scene.name, used_names)
    scene.name = new_name
    scene.save(update_fields=['name'])
    used_names.add(new_name)


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0008_add_ptz_calibration_to_cam'),
  ]

  operations = [
    migrations.AlterField(
      model_name="scene",
      name="name",
      field=models.CharField(max_length=200, unique=True, validators=[validate_scene_name]),
    ),
    migrations.RunPython(sanitize_legacy_scene_names, migrations.RunPython.noop),
    migrations.AddConstraint(
      model_name='scene',
      constraint=models.CheckConstraint(
        condition=(
          models.Q(name__regex=SCENE_NAME_DB_PATTERN)
          & ~models.Q(name__startswith='.')
          & ~models.Q(name__contains='..')
        ),
        name='manager_scene_valid_name',
      ),
    ),
  ]
