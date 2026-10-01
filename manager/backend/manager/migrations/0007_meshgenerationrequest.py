# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

  dependencies = [
    ("manager", "0006_childscene_transform_source_visual"),
  ]

  operations = [
    migrations.CreateModel(
      name="MeshGenerationRequest",
      fields=[
        (
          "request_id",
          models.CharField(max_length=128, primary_key=True, serialize=False),
        ),
        (
          "state",
          models.CharField(
            choices=[
              ("in_progress", "In progress"),
              ("complete", "Complete"),
              ("failed", "Failed"),
            ],
            default="in_progress",
            max_length=32,
          ),
        ),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        (
          "scene",
          models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE,
            related_name="mesh_generation_requests",
            to="manager.scene",
          ),
        ),
      ],
    ),
  ]
