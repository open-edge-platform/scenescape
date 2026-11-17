# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Standalone transport tests; no native geometry, database, or stack required."""

import sys
from importlib import import_module
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
    MCP_MAX_REQUEST_SIZE=64 * 1024,
    USE_TZ=True,
  )
django.setup()

from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

# Bootstrap only the query module with a model placeholder. Tests patch
# queries.Scene directly; the real Manager models require native dependencies.
with pytest.MonkeyPatch.context() as bootstrap:
  bootstrap.setitem(sys.modules, 'manager.models', SimpleNamespace(Scene=None))
  import_module('mcp_server.queries')


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
