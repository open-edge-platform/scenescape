# manager/src/manager/migrations/0002_add_cached_tripwires_to_childscene.py
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models


def add_cached_tripwires_if_missing(apps, schema_editor):
  ChildScene = apps.get_model("manager", "ChildScene")
  table = ChildScene._meta.db_table
  column = "cached_tripwires"

  with schema_editor.connection.cursor() as cursor:
    existing = {
      c.name for c in schema_editor.connection.introspection.get_table_description(cursor, table)
    }

  if column in existing:
    return

  field = models.JSONField(blank=True, default=list, verbose_name="Cached remote tripwires")
  field.set_attributes_from_name(column)
  schema_editor.add_field(ChildScene, field)


class Migration(migrations.Migration):
  dependencies = [
    ("manager", "0001_initial"),
  ]

  operations = [
    migrations.SeparateDatabaseAndState(
      database_operations=[
        migrations.RunPython(add_cached_tripwires_if_missing, reverse_code=migrations.RunPython.noop),
      ],
      state_operations=[
        migrations.AddField(
          model_name="childscene",
          name="cached_tripwires",
          field=models.JSONField(blank=True, default=list, verbose_name="Cached remote tripwires"),
        ),
      ],
    ),
  ]
