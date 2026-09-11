# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from django.conf import settings

def selected_settings(request):
  return {
    'APP_VERSION_NUMBER': settings.APP_VERSION_NUMBER,
    'APP_GIT_COMMIT': settings.APP_GIT_COMMIT,
    'APP_PROPER_NAME': settings.APP_PROPER_NAME,
    'APP_BASE_NAME': settings.APP_BASE_NAME,
    'KUBERNETES_SERVICE_HOST': settings.KUBERNETES_SERVICE_HOST,
  }
