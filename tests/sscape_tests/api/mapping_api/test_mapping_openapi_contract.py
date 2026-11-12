# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAPI contract checks for the mapping REST API.

``test_mapping_matches_openapi_contract`` calls the Flask app and runs
response schema, status code, content type, and response header conformance.
``reconstruct3D`` is excluded from generated calls because it starts an
asynchronous reconstruction job; it remains in the route inventory.
``test_flask_routes_match_spec_operations`` compares every ``/v1`` route with
``mapping-api.yaml``. Neither test rewrites the spec.

The mapping test image does not ship the OpenAPI document; this module is
skipped there and enforced from a full checkout (``make check-mapping-contract``).
"""

from pathlib import Path

import pytest

from api_service_base import app
from tests.sscape_tests.api.common import (
  CONTRACT_CHECKS,
  assert_operations_match,
  assert_server_prefix_documented,
  flask_operations,
  load_wsgi_schema,
  skip_if_spec_missing,
  spec_operations,
)

_SPEC_RELATIVE = Path(
  "docs/user-guide/microservices/mapping-service/_assets/mapping-api.yaml")
_SPEC_PATH = skip_if_spec_missing(_SPEC_RELATIVE, start=Path(__file__))

# Matches servers[].url, which already ends in /v1. Spec paths are relative to that.
API_PREFIX = "/v1"
schema = load_wsgi_schema(
  _SPEC_PATH, app, exclude_operation_ids=("reconstruct3D",))


@pytest.fixture(autouse=True)
def _loaded_model(mock_model, monkeypatch):
  """Keep a mocked, already-loaded model so calls see a ready service.

  This checks contract conformance, not model-not-loaded error paths.
  """
  mock_model.is_loaded = True
  monkeypatch.setattr("api_service_base.loaded_model", mock_model)
  monkeypatch.setattr("api_service_base.model_name", "mock_model")


@schema.parametrize()
def test_mapping_matches_openapi_contract(case):
  """Documented operations other than reconstruct3D must pass the four checks."""
  case.call_and_validate(checks=CONTRACT_CHECKS)


def test_flask_routes_match_spec_operations():
  """Flask /v1 routes must equal the operations documented in mapping-api.yaml."""
  assert_server_prefix_documented(_SPEC_PATH, API_PREFIX)
  routed, outside_prefix = flask_operations(app, API_PREFIX)
  documented = spec_operations(_SPEC_PATH)
  assert_operations_match(
    routed,
    documented,
    empty_message="no /v1 routes registered on the mapping Flask app",
    outside_prefix=outside_prefix,
    api_prefix=API_PREFIX,
  )
