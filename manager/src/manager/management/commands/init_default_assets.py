# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.core.management.base import BaseCommand

from manager.models import Asset3D


DEFAULT_ASSETS = [
  {
    "name": "vehicle",
    "x_size": 4.04,
    "y_size": 1.66,
    "z_size": 1.55,
    "tracking_radius": 3.0,
    "mark_color": "#0099ff",
    "shift_type": 1,
  },
  {
    "name": "cyclist",
    "x_size": 1.85,
    "y_size": 0.65,
    "z_size": 1.84,
    "tracking_radius": 2.0,
    "mark_color": "#f39c12",
    "shift_type": 1,
  },
]


class Command(BaseCommand):
  help = "Ensure default Asset3D objects (vehicle, cyclist) exist in the objects library."

  def handle(self, *args, **options):
    for asset in DEFAULT_ASSETS:
      name = asset["name"]
      defaults = {k: v for k, v in asset.items() if k != "name"}
      obj, created = Asset3D.objects.get_or_create(name=name, defaults=defaults)
      if created:
        self.stdout.write(f"Created Asset3D: {name}")
      else:
        self.stdout.write(f"Asset3D already exists: {name} (skipped)")
