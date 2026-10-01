# SPDX-FileCopyrightText: (C) 2021 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Django template context — thin wrappers over services.ui_bootstrap."""

from django.conf import settings

from manager.services.ui_bootstrap import build_chrome_bootstrap, user_auth_token

# Re-export for callers / tests that import chrome_bootstrap from here.
chrome_bootstrap = build_chrome_bootstrap


def selected_settings(request):
  return {
    'APP_VERSION_NUMBER': settings.APP_VERSION_NUMBER,
    'APP_GIT_COMMIT': settings.APP_GIT_COMMIT,
    'DOCS_VERSION': settings.DOCS_VERSION,
    'APP_PROPER_NAME': settings.APP_PROPER_NAME,
    'APP_BASE_NAME': settings.APP_BASE_NAME,
    'KUBERNETES_SERVICE_HOST': settings.KUBERNETES_SERVICE_HOST,
    'EXPOSE_TEST_HOOKS': settings.EXPOSE_TEST_HOOKS,
    'SS_AUTH_TOKEN': user_auth_token(getattr(request, "user", None)),
  }
