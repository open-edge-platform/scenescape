# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations


class Migration(migrations.Migration):
  dependencies = [
    ('manager', '0007_geospatial_glb_fields'),
    ('manager', '0011_cam_pose_provenance'),
  ]

  operations = []
