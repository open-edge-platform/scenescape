# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAPI contract checks for the autocalibration REST API.

``test_autocalibration_matches_openapi_contract`` calls CameraCalibrationApi
and runs response schema, status code, content type, and response header
conformance. ``test_flask_routes_match_spec_operations`` compares every
``/v1`` route with ``autocalibration-api.yaml``. Neither test rewrites the spec.
"""

from pathlib import Path

from auto_camera_calibration_api import CameraCalibrationApi
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
  "docs/user-guide/microservices/auto-calibration/_assets/autocalibration-api.yaml")
_SPEC_PATH = skip_if_spec_missing(_SPEC_RELATIVE, start=Path(__file__))

# Matches servers[].url, which already ends in /v1. Spec paths are relative to that.
API_PREFIX = "/v1"
_api = CameraCalibrationApi(calibrationContext=None)
schema = load_wsgi_schema(_SPEC_PATH, _api.app)


@schema.parametrize()
def test_autocalibration_matches_openapi_contract(case):
  """Every documented operation must satisfy the four OpenAPI response checks."""
  case.call_and_validate(checks=CONTRACT_CHECKS)


def test_flask_routes_match_spec_operations():
  """Flask /v1 routes must equal the operations documented in autocalibration-api.yaml."""
  assert_server_prefix_documented(_SPEC_PATH, API_PREFIX)
  routed, outside_prefix = flask_operations(_api.app, API_PREFIX)
  documented = spec_operations(_SPEC_PATH)
  assert_operations_match(
    routed,
    documented,
    empty_message="no /v1 routes registered on CameraCalibrationApi",
    outside_prefix=outside_prefix,
    api_prefix=API_PREFIX,
  )
