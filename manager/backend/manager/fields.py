# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from django.db import models
from django.conf import settings

if 'postgresql' in settings.DATABASES['default']['ENGINE']:
  from django.contrib.postgres.fields import ArrayField

  class ListField(ArrayField):
    def __init__(self, *args, **kwargs):
      kwargs.setdefault('base_field', models.FloatField())
      kwargs.setdefault('default', list)
      super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
      if value is None:
        return []
      return value

    def get_prep_value(self, value):
      if value is None:
        return []
      return list(value)

else:
  class ListField(models.JSONField):
    """Robust JSONField for list of floats, handles double-encoded JSON."""
    def from_db_value(self, value, expression, connection):
      if value is None:
        return []
      while isinstance(value, str):
        try:
          value = json.loads(value)
        except json.JSONDecodeError:
          return []
      if isinstance(value, list):
        return [float(v) for v in value if isinstance(v, (int, float, str))]
      return []

    def get_prep_value(self, value):
      """Prepare list of floats for DB storage."""
      if value is None:
        return []
      while isinstance(value, str):
        try:
          value = json.loads(value)
        except json.JSONDecodeError:
          return []
      if isinstance(value, list):
        result = []
        for v in value:
          try:
            result.append(float(v))
          except (ValueError, TypeError):
            continue
        return result
      return []
