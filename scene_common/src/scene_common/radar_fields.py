# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Field lists for Radar Manager serializers and scene import."""

RADAR_COMMON_FIELDS = (
  "name",
  "scale",
)

RADAR_SERIALIZER_FIELDS = [
  'uid', 'name', 'sensor_id', 'transform_type', 'transforms',
  'translation', 'rotation', 'scale', 'scene',
]
