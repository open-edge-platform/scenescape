# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations


def add_default_asset3d_objects(apps, schema_editor):
  """Populate the Asset3D objects library with default vehicle and cyclist entries.

  Sizes are derived from observed LiDAR detections:
    vehicle  – avg of three detections: x=4.04 m, y=1.66 m, z=1.55 m
    cyclist  – single detection:        x=1.85 m, y=0.65 m, z=1.84 m
  """
  Asset3D = apps.get_model("manager", "Asset3D")

  Asset3D.objects.get_or_create(
    name="vehicle",
    defaults={
      "x_size": 4.04,
      "y_size": 1.66,
      "z_size": 1.55,
      "tracking_radius": 3.0,
      "mark_color": "#0099ff",
      "shift_type": 1,
    },
  )

  Asset3D.objects.get_or_create(
    name="cyclist",
    defaults={
      "x_size": 1.85,
      "y_size": 0.65,
      "z_size": 1.84,
      "tracking_radius": 2.0,
      "mark_color": "#f39c12",
      "shift_type": 1,
    },
  )


def remove_default_asset3d_objects(apps, schema_editor):
  Asset3D = apps.get_model("manager", "Asset3D")
  Asset3D.objects.filter(name__in=["vehicle", "cyclist"]).delete()


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0001_initial"),
  ]

  operations = [
    migrations.RunPython(
      add_default_asset3d_objects,
      reverse_code=remove_default_asset3d_objects,
    ),
  ]
