# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations

# Frozen snapshot of manager.default_assets.DEFAULT_ASSETS at migration authoring
# time. Do not import the live module here — historical migrations must not
# depend on app code that can move or change. Ongoing / idempotent seeding uses
# ``init_default_assets`` + manager.default_assets (single live source of truth).
_FROZEN_DEFAULT_ASSETS = [
  {
    "name": "vehicle",
    "x_size": 4.04,
    "y_size": 1.66,
    "z_size": 1.55,
    "tracking_radius": 10.0,
    "mark_color": "#0099ff",
    "shift_type": 1,
    "rotation_from_velocity": True,
  },
  {
    "name": "cyclist",
    "x_size": 1.85,
    "y_size": 0.65,
    "z_size": 1.84,
    "tracking_radius": 2.0,
    "mark_color": "#f39c12",
    "shift_type": 1,
    "rotation_from_velocity": True,
  },
]


def add_default_asset3d_objects(apps, schema_editor):
  """Seed default Asset3D rows from the frozen snapshot above."""
  Asset3D = apps.get_model("manager", "Asset3D")
  for asset in _FROZEN_DEFAULT_ASSETS:
    defaults = {k: v for k, v in asset.items() if k != "name"}
    Asset3D.objects.get_or_create(name=asset["name"], defaults=defaults)


def remove_default_asset3d_objects(apps, schema_editor):
  Asset3D = apps.get_model("manager", "Asset3D")
  Asset3D.objects.filter(
    name__in=[a["name"] for a in _FROZEN_DEFAULT_ASSETS]
  ).delete()


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
