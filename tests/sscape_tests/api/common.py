# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared OpenAPI contract helpers for the manager, mapping, and autocalibration tests.

Spec files are located by walking up from the caller until the repository
root (``version.txt``) or the relative document is found. Do not count
``Path.parents`` — these tests have moved, and a fixed index resolves to the
wrong directory.
"""

from pathlib import Path
from urllib.parse import urlsplit
import re

import pytest
import schemathesis
import yaml
from schemathesis.checks import (
  content_type_conformance,
  response_headers_conformance,
  response_schema_conformance,
  status_code_conformance,
)

# Explicit set passed to case.call_and_validate. Passing checks= replaces
# schemathesis defaults, so every contract test must use this list.
CONTRACT_CHECKS = [
  response_schema_conformance,
  status_code_conformance,
  content_type_conformance,
  response_headers_conformance,
]

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

_FLASK_PARAM = re.compile(r"<(?:[^:>]+:)?([^>]+)>")
_SPEC_PARAM = re.compile(r"\{[^}]*\}")


def repo_root(start=None):
  """Return the repository root that contains ``version.txt`` and ``docs``."""
  here = _as_dir(start or Path(__file__))
  for parent in [here, *here.parents]:
    if (parent / "version.txt").is_file() and (parent / "docs").is_dir():
      return parent
  raise FileNotFoundError("repository root not found (version.txt)")


def find_repo_file(relative, start=None):
  """Return ``relative`` under an ancestor of ``start``, or None if missing."""
  relative = Path(relative)
  here = _as_dir(start or Path(__file__))
  for parent in [here, *here.parents]:
    candidate = parent / relative
    if candidate.is_file():
      return candidate
  return None


def skip_if_spec_missing(relative, start=None):
  """Return the committed spec, or skip the importing test module if absent."""
  found = find_repo_file(relative, start=start)
  if found is None:
    pytest.skip(
      f"{relative} is not available in this environment",
      allow_module_level=True,
    )
  return found


def load_openapi_document(spec_path):
  """Load an OpenAPI YAML document."""
  document = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
  if not isinstance(document, dict):
    raise ValueError(f"{spec_path} is not an OpenAPI mapping")
  return document


def load_wsgi_schema(spec_path, app, exclude_operation_ids=()):
  """Load a spec and bind it to a WSGI app before operations are built.

  ``schema.app`` must be set on the object that ``parametrize`` iterates.
  Without it, schemathesis calls ``servers[].url`` over the network and the
  conformance checks do not exercise this process.
  """
  if app is None:
    raise ValueError("WSGI app is required so conformance checks call the app")
  schema = schemathesis.openapi.from_path(spec_path)
  for operation_id in exclude_operation_ids:
    schema = schema.exclude(operation_id=operation_id)
  schema.app = app
  return schema


def spec_operations(spec_path, collapse_params=False):
  """Return ``{(path, METHOD)}`` for every HTTP operation in the document."""
  paths = load_openapi_document(spec_path).get("paths") or {}
  operations = set()
  for path, item in paths.items():
    if not isinstance(item, dict):
      continue
    normalized = _SPEC_PARAM.sub("{}", path) if collapse_params else path
    for method, operation in item.items():
      if method in HTTP_METHODS and isinstance(operation, dict):
        operations.add((normalized, method.upper()))
  return operations


def flask_rule_to_spec_path(rule, api_prefix):
  """Turn a Flask rule into a spec path, e.g. ``/v1/health`` -> ``/health``."""
  path = rule.removeprefix(api_prefix)
  if not path.startswith("/"):
    path = "/" + path
  return _FLASK_PARAM.sub(r"{\1}", path)


def flask_operations(app, api_prefix):
  """Return ``({(path, METHOD)}, [rules outside the prefix])`` for a Flask app."""
  operations = set()
  outside_prefix = []
  prefix = api_prefix + "/"
  for rule in app.url_map.iter_rules():
    if rule.endpoint == "static" or rule.rule.startswith("/static"):
      continue
    if not rule.rule.startswith(prefix):
      outside_prefix.append(rule.rule)
      continue
    path = flask_rule_to_spec_path(rule.rule, api_prefix)
    for method in rule.methods:
      if method.lower() in HTTP_METHODS:
        operations.add((path, method.upper()))
  return operations, outside_prefix


def assert_server_prefix_documented(spec_path, suffix):
  """Fail unless some ``servers[].url`` path is the prefix stripped from app routes.

  Spec paths are relative to each server. The in-process app implements the
  direct prefix (``/v1`` or ``/api/v1``). Alternate servers, such as the Apache
  reverse proxy, may use a different base path and are not app routes.
  """
  servers = load_openapi_document(spec_path).get("servers") or []
  assert servers, f"{spec_path} has no servers"
  expected = suffix.rstrip("/")
  paths = []
  for server in servers:
    url = server.get("url", "") if isinstance(server, dict) else ""
    paths.append(urlsplit(url).path.rstrip("/"))
  assert expected in paths, (
    f"no servers[].url path is {expected}; route comparison would not match "
    f"spec paths. Found {paths}"
  )


def assert_operations_match(
    routed, documented, empty_message, outside_prefix=None, api_prefix=None):
  """Fail when implemented operations and the OpenAPI document disagree."""
  assert routed, empty_message
  if outside_prefix is not None:
    assert not outside_prefix, f"routes outside {api_prefix}: {sorted(outside_prefix)}"
  extra = sorted(routed - documented)
  missing = sorted(documented - routed)
  assert not extra and not missing, (
    f"routed but not documented: {extra}; documented but not routed: {missing}"
  )


def _as_dir(start):
  path = Path(start).resolve()
  return path.parent if path.is_file() else path
