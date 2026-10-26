# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Checks for the shared OpenAPI contract helpers.

These do not call the services. They verify that the committed documents can
be found after the tests moved, and that route comparison reports both extra
and missing operations.
"""

from pathlib import Path

import pytest
from flask import Flask

from tests.sscape_tests.api.common import (
  CONTRACT_CHECKS,
  assert_operations_match,
  assert_server_prefix_documented,
  find_repo_file,
  flask_operations,
  flask_rule_to_spec_path,
  repo_root,
  spec_operations,
)

_SPECS = {
  "manager": (
    "docs/user-guide/api-docs/api.yaml",
    "/api/v1",
  ),
  "mapping": (
    "docs/user-guide/microservices/mapping-service/_assets/mapping-api.yaml",
    "/v1",
  ),
  "autocalibration": (
    "docs/user-guide/microservices/auto-calibration/_assets/autocalibration-api.yaml",
    "/v1",
  ),
}


def test_contract_checks_are_the_four_conformance_checks():
  """The shared list must be exactly the four schemathesis conformance checks."""
  assert [check.__name__ for check in CONTRACT_CHECKS] == [
    "response_schema_conformance",
    "status_code_conformance",
    "content_type_conformance",
    "response_headers_conformance",
  ]


def test_committed_specs_are_found_from_nested_tests():
  """Walking parents must find each spec, not a fixed Path.parents index."""
  root = repo_root(Path(__file__))
  for relative, _suffix in _SPECS.values():
    found = find_repo_file(relative, start=Path(__file__))
    assert found == root / relative
    assert found.is_file()


def test_server_urls_document_the_prefix_route_audits_strip():
  """The direct server prefix must exist or stripping it would hide route drift."""
  for relative, suffix in _SPECS.values():
    spec_path = find_repo_file(relative, start=Path(__file__))
    assert_server_prefix_documented(spec_path, suffix)


def test_mapping_reconstruct_operation_exists_for_exclusion():
  """Exclusion is only valid if the operation id is still in the document."""
  spec_path = find_repo_file(_SPECS["mapping"][0], start=Path(__file__))
  operations = spec_operations(spec_path)
  assert ("/reconstruction", "POST") in operations


def test_flask_rule_conversion_keeps_parameter_names():
  assert flask_rule_to_spec_path("/v1/health", "/v1") == "/health"
  assert flask_rule_to_spec_path(
    "/v1/scenes/<sceneId>/registration", "/v1") == "/scenes/{sceneId}/registration"
  assert flask_rule_to_spec_path(
    "/v1/reconstruction/status/<string:request_id>", "/v1"
  ) == "/reconstruction/status/{request_id}"


def test_flask_operations_match_rules_and_flag_routes_outside_prefix():
  app = Flask(__name__)

  @app.route("/v1/health", methods=["GET"])
  def health():
    return "ok"

  @app.route("/v1/scenes/<sceneId>/registration", methods=["GET", "POST"])
  def registration(sceneId):
    return sceneId

  @app.route("/ready", methods=["GET"])
  def ready():
    return "ready"

  routed, outside = flask_operations(app, "/v1")
  assert routed == {
    ("/health", "GET"),
    ("/scenes/{sceneId}/registration", "GET"),
    ("/scenes/{sceneId}/registration", "POST"),
  }
  assert outside == ["/ready"]


def test_matching_operations_pass():
  operations = {("/health", "GET")}
  assert_operations_match(operations, operations, empty_message="no routes")


def test_route_drift_reports_extra_and_missing_operations():
  with pytest.raises(AssertionError, match="routed but not documented"):
    assert_operations_match(
      {("/health", "GET"), ("/extra", "POST")},
      {("/health", "GET"), ("/missing", "DELETE")},
      empty_message="no routes",
    )


def test_empty_route_set_fails():
  with pytest.raises(AssertionError, match="no /v1 routes"):
    assert_operations_match(set(), {("/health", "GET")}, empty_message="no /v1 routes")


def test_routes_outside_prefix_fail():
  with pytest.raises(AssertionError, match="routes outside"):
    assert_operations_match(
      {("/health", "GET")},
      {("/health", "GET")},
      empty_message="no routes",
      outside_prefix=["/ready"],
      api_prefix="/v1",
    )
