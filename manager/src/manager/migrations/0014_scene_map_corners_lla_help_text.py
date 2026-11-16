# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import manager.validators
from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0013_clear_glb_trs_matrix'),
  ]

  operations = [
    migrations.AlterField(
      model_name='scene',
      name='map_corners_lla',
      field=models.JSONField(blank=True, default=None, help_text="Provide the array of four map corners geospatial coordinates (lat, long, alt).\nRequired only if 'Output geospatial coordinates' is set to `Yes`.\nExpected order: starting from the bottom-left corner, either counterclockwise or clockwise.\nExpected JSON format: '[ [lat1, lon1, alt1], [lat2, lon2, alt2], [lat3, lon3, alt3], [lat4, lon4, alt4] ]'", null=True, validators=[manager.validators.validate_map_corners_lla], verbose_name='Geospatial coordinates of the four map corners in JSON format'),
    ),
  ]
