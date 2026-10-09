# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re

from django.db import migrations, models

import manager.validators

# Keep in sync with manager.validators.SCENE_NAME_PATTERN / validate_scene_name.
SCENE_NAME_PATTERN = r'^[\w \-.]+$'
SCENE_NAME_RE = re.compile(SCENE_NAME_PATTERN)


def _is_valid_scene_name(name):
  return bool(name) and bool(SCENE_NAME_RE.fullmatch(name)) and not name.startswith('.') and '..' not in name


def _sanitize_scene_name(name, used_names):
  cleaned = re.sub(r'[^\w \-.]', '_', name or '')
  cleaned = cleaned.lstrip('.')
  while '..' in cleaned:
    cleaned = cleaned.replace('..', '_')
  cleaned = cleaned.strip() or 'scene'
  cleaned = cleaned[:200]
  candidate = cleaned
  suffix = 1
  while candidate in used_names or not _is_valid_scene_name(candidate):
    suffix_str = f'_{suffix}'
    candidate = f"{cleaned[:200 - len(suffix_str)]}{suffix_str}"
    suffix += 1
  return candidate


def sanitize_legacy_scene_names(apps, schema_editor):
  Scene = apps.get_model('manager', 'Scene')
  used_names = set(Scene.objects.values_list('name', flat=True))
  for scene in Scene.objects.all():
    if _is_valid_scene_name(scene.name):
      continue
    used_names.discard(scene.name)
    new_name = _sanitize_scene_name(scene.name, used_names)
    scene.name = new_name
    scene.save(update_fields=['name'])
    used_names.add(new_name)


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0004_add_cached_sensors_to_childscene'),

  ]

  operations = [
    migrations.AlterField(
      model_name="scene",
      name="name",
      field=models.CharField(max_length=200, unique=True, validators=[manager.validators.validate_scene_name]),
    ),
    migrations.RunPython(sanitize_legacy_scene_names, migrations.RunPython.noop),
    migrations.AddConstraint(
      model_name='scene',
      constraint=models.CheckConstraint(
        condition=(
          models.Q(name__regex=SCENE_NAME_PATTERN)
          & ~models.Q(name__startswith='.')
          & ~models.Q(name__contains='..')
        ),
        name='manager_scene_valid_name',
      ),
    ),
  ]
