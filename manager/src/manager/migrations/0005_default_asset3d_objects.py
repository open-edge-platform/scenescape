# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations


def add_default_asset3d_objects(apps, schema_editor):
  """Seed default Asset3D rows using the shared DEFAULT_ASSETS definition.

  See manager.default_assets for sizes/colors and lifecycle notes. The
  init_default_assets management command uses the same source and re-ensures
  these rows on every manager start.
  """
  # Import at runtime so the migration tracks current seed values from the
  # single source of truth (get_or_create only applies defaults on create).
  from manager.default_assets import DEFAULT_ASSETS

  Asset3D = apps.get_model("manager", "Asset3D")
  for asset in DEFAULT_ASSETS:
    defaults = {k: v for k, v in asset.items() if k != "name"}
    Asset3D.objects.get_or_create(name=asset["name"], defaults=defaults)


def remove_default_asset3d_objects(apps, schema_editor):
  from manager.default_assets import DEFAULT_ASSETS

  Asset3D = apps.get_model("manager", "Asset3D")
  Asset3D.objects.filter(name__in=[a["name"] for a in DEFAULT_ASSETS]).delete()


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0004_add_cached_sensors_to_childscene"),
  ]

  operations = [
    migrations.RunPython(
      add_default_asset3d_objects,
      reverse_code=remove_default_asset3d_objects,
    ),
  ]
