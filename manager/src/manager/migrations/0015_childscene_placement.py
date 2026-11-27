# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0014_scene_glb_apply_all'),
  ]

  operations = [
    migrations.AddField(
      model_name='childscene',
      name='placement',
      field=models.JSONField(
        blank=True, default=None, editable=False, null=True,
        verbose_name='Placement provenance',
      ),
    ),
  ]
