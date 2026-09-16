#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import django.core.validators
import manager.validators
from django.db import migrations, models


class Migration(migrations.Migration):

  dependencies = [
      ('manager', '0004_add_mapping_bundle'),
  ]

  operations = [
      migrations.AddField(
          model_name='scene',
          name='arkit_mapping_bundle',
          field=models.FileField(
              blank=True, default=None, null=True, upload_to='',
              validators=[django.core.validators.FileExtensionValidator(['zip']),
                          manager.validators.validate_arkit_mapping_bundle_zip],
              verbose_name='Shared ARKit mapping session artifacts (ARWorldMap + metadata) as a .zip bundle'),
      ),
      migrations.AddField(
          model_name='scene',
          name='arkit_mapping_bundle_updated',
          field=models.DateTimeField(
              blank=True, default=None, editable=False, null=True,
              verbose_name='ARKit mapping bundle last updated'),
      ),
      migrations.AddField(
          model_name='scene',
          name='arkit_mapping_bundle_contributor',
          field=models.CharField(
              blank=True, default='', editable=False, max_length=200,
              verbose_name='ARKit mapping bundle last contributor'),
      ),
  ]
