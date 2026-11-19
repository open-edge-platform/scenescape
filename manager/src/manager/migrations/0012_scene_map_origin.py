# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scene map image origin: world coordinates of the 2D map's bottom-left corner."""

from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
    ('manager', '0011_cam_pose_provenance'),
  ]

  # Released thumbnails were rendered with their bottom-left corner at world (0, 0).
  operations = [
    migrations.AddField(
      model_name='scene',
      name='map_origin_x',
      field=models.FloatField(default=0.0, editable=False, verbose_name='Map image origin X (meters)'),
    ),
    migrations.AddField(
      model_name='scene',
      name='map_origin_y',
      field=models.FloatField(default=0.0, editable=False, verbose_name='Map image origin Y (meters)'),
    ),
  ]
