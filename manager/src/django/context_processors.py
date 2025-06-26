# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from django.conf import settings

def selected_settings(request):
  return {
    'APP_VERSION_NUMBER': settings.APP_VERSION_NUMBER,
    'APP_PROPER_NAME': settings.APP_PROPER_NAME,
    'APP_BASE_NAME': settings.APP_BASE_NAME,
    'KUBERNETES_SERVICE_HOST': settings.KUBERNETES_SERVICE_HOST,
  }
