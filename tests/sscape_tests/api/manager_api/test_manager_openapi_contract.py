# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Manager OpenAPI contract checks.

``test_manager_matches_openapi_contract`` calls the Django WSGI app and runs
response schema, status code, content type, and response header conformance.
``test_url_routes_match_spec_operations`` compares routed ``api/v1`` methods
with ``api.yaml``. Neither test rewrites the spec.
"""

from pathlib import Path

import pytest
from django.core.wsgi import get_wsgi_application
from hypothesis import HealthCheck, settings

from tests.sscape_tests.api.common import (
  CONTRACT_CHECKS,
  HTTP_METHODS,
  assert_operations_match,
  assert_server_prefix_documented,
  load_openapi_document,
  load_wsgi_schema,
  skip_if_spec_missing,
  spec_operations,
)

_SPEC_RELATIVE = Path("docs/user-guide/api-docs/api.yaml")
_SPEC_PATH = skip_if_spec_missing(_SPEC_RELATIVE, start=Path(__file__))

schema = load_wsgi_schema(_SPEC_PATH, get_wsgi_application())

API_PREFIX = "api/v1"
SERVER_PREFIX = "/api/v1"
# Browser-session endpoints, documented in api.yaml as out of scope.
UNDOCUMENTED_ROUTES = {"/save-geospatial-snapshot/", "/model-directory/"}


@pytest.fixture(params=["superuser", "regular_user"])
def api_token(request, transactional_db):
  """Token for a superuser and for a regular user, who gets 403 on writes."""
  from django.contrib.auth.models import User
  from rest_framework.authtoken.models import Token
  if request.param == "superuser":
    user = User.objects.create_superuser("contract_admin", "a@example.com", "x")
  else:
    user = User.objects.create_user("contract_user", "u@example.com", "x")
  return Token.objects.create(user=user).key


@pytest.mark.django_db(transaction=True)
@schema.parametrize()
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None,
          max_examples=5, derandomize=True)
def test_manager_matches_openapi_contract(case, api_token):
  """Every documented operation must satisfy the four OpenAPI response checks."""
  case.call_and_validate(
    headers={"Authorization": f"Token {api_token}"}, checks=CONTRACT_CHECKS)


def _route_to_spec_path(route):
  """Turn a URL pattern string into a spec path, e.g. 'api/v1/(camera)/([^/]+)$' -> '/camera/{}'."""
  path = ""
  depth = 0
  group = ""
  for char in route.removeprefix(API_PREFIX).rstrip("$"):
    if char == "(":
      depth += 1
    if depth == 0:
      path += char
    else:
      group += char
    if char == ")":
      depth -= 1
      if depth == 0:
        path += group[1:-1] if group[1:-1].isalpha() else "{}"
        group = ""
  return path


def _resolver_operations():
  """Return {(path, METHOD)} for every api/v1 route registered in the URL resolver."""
  from django.urls import URLResolver, get_resolver

  operations = set()

  def walk(patterns, prefix=""):
    for entry in patterns:
      route = prefix + str(entry.pattern)
      if isinstance(entry, URLResolver):
        walk(entry.url_patterns, route)
        continue
      if not route.startswith(API_PREFIX):
        continue
      path = _route_to_spec_path(route)
      if path in UNDOCUMENTED_ROUTES:
        continue
      view_class = entry.callback.view_class
      allowed = entry.callback.view_initkwargs.get(
        "http_method_names", view_class.http_method_names)
      for method in allowed:
        if method in HTTP_METHODS and hasattr(view_class, method):
          operations.add((path, method.upper()))

  walk(get_resolver().url_patterns)
  return operations


def test_url_routes_match_spec_operations():
  """The (path, method) pairs routed by Django must equal those documented in api.yaml."""
  assert_server_prefix_documented(_SPEC_PATH, SERVER_PREFIX)
  routed = _resolver_operations()
  documented = spec_operations(_SPEC_PATH, collapse_params=True)
  assert_operations_match(
    routed, documented, empty_message="no api/v1 routes found in the URL resolver")


def test_patched_schemas_match_base_schemas():
  """Patched<X> (partial update bodies) must declare the same properties as <X>."""
  schemas = load_openapi_document(_SPEC_PATH)["components"]["schemas"]
  patched = [name for name in schemas if name.startswith("Patched")]
  assert patched
  for name in patched:
    base = name[len("Patched"):]
    assert schemas[name]["properties"] == schemas[base]["properties"], f"{name} differs from {base}"
    assert "required" not in schemas[name], f"{name} must not require fields"
