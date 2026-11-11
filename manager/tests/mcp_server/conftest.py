# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Standalone transport tests; no native geometry, database, or stack required."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import django
import pytest
from django.conf import settings

# The root tests/conftest.py applies only to tests/, not manager/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
if not settings.configured:
  settings.configure(
    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes',
                    'rest_framework', 'rest_framework.authtoken'],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    ALLOWED_HOSTS=['testserver'], ROOT_URLCONF='mcp_server.urls',
    REST_FRAMEWORK={'UNAUTHENTICATED_USER': None},
    USE_TZ=True,
  )
django.setup()

from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


@pytest.fixture
def user() -> SimpleNamespace:
  """Use an authenticated user stub without persisting credentials."""
  return SimpleNamespace(pk=1, is_authenticated=True, is_active=True)


@pytest.fixture
def client(user: SimpleNamespace) -> APIClient:
  """Exercise real token authentication with its database lookup mocked."""
  cache.clear()
  with patch.object(Token.objects, 'select_related', return_value=Token.objects), \
       patch.object(Token.objects, 'get', return_value=SimpleNamespace(user=user)):
    yield APIClient(enforce_csrf_checks=True)
  cache.clear()
