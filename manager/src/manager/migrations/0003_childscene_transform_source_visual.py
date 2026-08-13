# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0002_childscene_transform_source'),
  ]

  operations = [
      migrations.AlterField(
          model_name='childscene',
          name='transform_source',
          field=models.CharField(
              blank=True,
              choices=[
                  ('manual', 'Manual'),
                  ('geospatial', 'Geospatial'),
                  ('visual', 'Visual'),
              ],
              default='manual',
              help_text="How the child pose was obtained. Geospatial links are recomputed when either scene's map corners or scale change. Visual (3D gizmo) and manual links are never auto-refreshed.",
              max_length=16,
          ),
      ),
  ]
