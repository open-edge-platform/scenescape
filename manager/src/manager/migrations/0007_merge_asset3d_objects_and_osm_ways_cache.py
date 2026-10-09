# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations


class Migration(migrations.Migration):
  """Merge the two independent 0005 migration branches introduced by merging
  main (0005_default_asset3d_objects) into this feature branch, which already
  had its own 0005/0006 OSM ways cache migrations."""

  dependencies = [
    ('manager', '0005_default_asset3d_objects'),
    ('manager', '0006_add_osm_ways_cache_bbox_to_scene'),
  ]

  operations = []
