# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Drop the legacy per-revision head pointer after backfill commits."""

from django.db import migrations


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0008_default_map_revision'),
  ]

  operations = [
      migrations.RemoveConstraint(
          model_name='scenemaprevision', name='unique_head_map_revision'),
      migrations.RemoveField(model_name='scenemaprevision', name='head'),
  ]
