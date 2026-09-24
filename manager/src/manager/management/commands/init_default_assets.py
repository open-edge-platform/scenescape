# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.core.management.base import BaseCommand

from manager.default_assets import DEFAULT_ASSETS
from manager.models import Asset3D


class Command(BaseCommand):
  help = (
    "Ensure default Asset3D objects (vehicle, cyclist) exist in the objects "
    "library. Defaults live in manager.default_assets (shared with migration 0005)."
  )

  def handle(self, *args, **options):
    for asset in DEFAULT_ASSETS:
      name = asset["name"]
      defaults = {k: v for k, v in asset.items() if k != "name"}
      obj, created = Asset3D.objects.get_or_create(name=name, defaults=defaults)
      if created:
        self.stdout.write(f"Created Asset3D: {name}")
      else:
        self.stdout.write(f"Asset3D already exists: {name} (skipped)")
