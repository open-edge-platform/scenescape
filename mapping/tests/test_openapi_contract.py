# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAPI contract test for the mapping service (schema-first).

Schemathesis loads the committed OpenAPI document and generates requests for
every declared operation, binding them directly to the Flask app's WSGI
interface (no running container needed). Only the conformance checks are
enabled -- response body, status code, content type, and headers must match
what the schema declares. General robustness/security checks (server errors
on unsupported methods, auth fuzzing, etc.) are intentionally excluded: this
test's only job is to catch drift between the schema and the implementation,
not to find unrelated implementation bugs.

This test never modifies the OpenAPI document. On drift, it fails with
Schemathesis's normal assertion output pointing at the violating operation;
a developer must then fix the implementation or update the spec by hand.

Known pre-existing drift (intentionally left failing, not fixed by this
test): GET /health and GET /models both document a response of
#/components/schemas/HealthResponse (requires "success"), but neither
handler's response includes a "success" key, and GET /models' body shape
(model/model_info/camera_pose_format) doesn't resemble HealthResponse at
all. Tracked as follow-up work, out of scope for adding this check.
"""

from pathlib import Path

import pytest
import schemathesis
from schemathesis.checks import (
  content_type_conformance,
  response_headers_conformance,
  response_schema_conformance,
  status_code_conformance,
)

from api_service_base import app

CONTRACT_CHECKS = [
  response_schema_conformance,
  status_code_conformance,
  content_type_conformance,
  response_headers_conformance,
]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_PATH = (
  _REPO_ROOT / "docs" / "user-guide" / "microservices" / "mapping-service" /
  "_assets" / "mapping-api.yaml"
)

# reconstruct3D's multipart encoding declares a comma-separated contentType
# ("image/jpeg, image/png"), which is valid OpenAPI 3.0.3 (a single value or a
# comma-separated list is explicitly allowed) and unenforced by the Flask
# handler (it never inspects per-file Content-Type), but Schemathesis's
# serializer lookup only matches exact single media-type strings, so it can't
# generate any example request for this operation. Excluded as a tooling gap,
# not schema drift; the other 3 operations stay fully covered.
schema = schemathesis.openapi.from_path(_SPEC_PATH).exclude(operation_id="reconstruct3D")
schema.app = app


@pytest.fixture(autouse=True)
def _loaded_model(mock_model, monkeypatch):
  """Keep a mocked, already-loaded model for the whole run so every operation
  behaves as it would in a healthy, ready service -- this test checks
  contract conformance, not model-not-loaded error paths."""
  mock_model.is_loaded = True
  monkeypatch.setattr("api_service_base.loaded_model", mock_model)
  monkeypatch.setattr("api_service_base.model_name", "mock_model")


@schema.parametrize()
def test_mapping_matches_openapi_contract(case):
  case.call_and_validate(checks=CONTRACT_CHECKS)
