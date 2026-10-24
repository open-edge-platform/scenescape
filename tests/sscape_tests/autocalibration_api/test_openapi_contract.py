# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAPI contract test for the autocalibration service (schema-first).

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
"""

from pathlib import Path

import schemathesis
from schemathesis.checks import (
  content_type_conformance,
  response_headers_conformance,
  response_schema_conformance,
  status_code_conformance,
)

from auto_camera_calibration_api import CameraCalibrationApi

CONTRACT_CHECKS = [
  response_schema_conformance,
  status_code_conformance,
  content_type_conformance,
  response_headers_conformance,
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_PATH = (
  _REPO_ROOT / "docs" / "user-guide" / "microservices" / "auto-calibration" /
  "_assets" / "autocalibration-api.yaml"
)

_api = CameraCalibrationApi(calibrationContext=None)
schema = schemathesis.openapi.from_path(_SPEC_PATH)
schema.app = _api.app


@schema.parametrize()
def test_autocalibration_matches_openapi_contract(case):
  case.call_and_validate(checks=CONTRACT_CHECKS)
