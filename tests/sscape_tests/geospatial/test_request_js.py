# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared requestJson helper in js/request.js."""

import json
import subprocess
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parent / "request_harness.js"


def run_request(url="/api/x", options=None, response=None, csrf="tok"):
  """Run requestJson against a fake fetch; returns {result|error, sent}."""
  scenario = {
    "url": url,
    "options": options or {},
    "response": response or {"status": 200, "body": {"ok": True}},
    "csrf": csrf,
  }
  proc = subprocess.run(
    ["node", str(_HARNESS)], input=json.dumps(scenario), capture_output=True, text=True, timeout=30)
  if proc.returncode != 0:
    raise RuntimeError(f"Harness exit {proc.returncode}: {proc.stderr}")
  return json.loads(proc.stdout)


@pytest.mark.usefixtures("node_runtime")
class TestRequestJson:
  """requestJson sends the CSRF header, encodes the body and normalises errors."""

  def test_json_body_gets_content_type_and_csrf_header(self):
    """A plain object body is sent as JSON with the page CSRF token."""
    out = run_request(options={"method": "POST", "body": {"a": 1}})
    assert out["result"] == {"ok": True}
    assert out["sent"] == [{
      "url": "/api/x", "method": "POST", "body": '{"a":1}',
      "headers": {"X-CSRFToken": "tok", "Content-Type": "application/json"},
    }]

  def test_form_data_is_sent_unchanged_without_content_type(self):
    """FormData keeps its own multipart content type."""
    out = run_request(options={"method": "POST", "body": "<FormData>"})
    assert out["sent"][0]["body"] == "<FormData>"
    assert out["sent"][0]["headers"] == {"X-CSRFToken": "tok"}

  def test_explicit_token_and_extra_headers(self):
    """An explicit token overrides the page token; extra headers are merged in."""
    out = run_request(options={"csrfToken": "cookie", "headers": {"Accept": "application/json"}})
    assert out["sent"][0]["headers"] == {"X-CSRFToken": "cookie", "Accept": "application/json"}

  def test_null_token_sends_no_csrf_header(self):
    """csrfToken=null (read-only requests) omits the header even when the page has a token."""
    out = run_request(options={"csrfToken": None})
    assert out["sent"][0]["headers"] == {}

  def test_missing_page_token_is_not_fatal_by_default(self):
    """Without a page token the request is still sent, with no CSRF header."""
    out = run_request(csrf=None)
    assert out["result"] == {"ok": True}
    assert out["sent"][0]["headers"] == {}

  def test_require_csrf_rejects_before_sending(self):
    """requireCsrf fails fast when no token is available."""
    out = run_request(csrf=None, options={"requireCsrf": True})
    assert out["error"]["message"] == "CSRF token not found"
    assert out["sent"] == []

  def test_no_content_response_resolves_to_empty_object(self):
    assert run_request(response={"status": 204})["result"] == {}

  def test_non_json_success_body_resolves_to_empty_object(self):
    assert run_request(response={"status": 200, "nonJson": True})["result"] == {}

  def test_error_carries_server_message_status_and_data(self):
    """A failed response rejects with the body's error text, the status and the parsed body."""
    body = {"error": "bad anchor", "glb_applied": True}
    out = run_request(response={"status": 409, "body": body})
    assert out["error"] == {"message": "bad anchor", "status": 409, "data": body}

  def test_error_without_body_error_uses_default_message(self):
    out = run_request(response={"status": 502, "nonJson": True})
    assert out["error"] == {"message": "Request failed (502)", "status": 502, "data": {}}

  def test_error_message_override(self):
    """errorMessage replaces the default text when the body has no error."""
    out = run_request(
      options={"errorMessageTemplate": "Preview failed ({status})"},
      response={"status": 500, "body": {}})
    assert out["error"]["message"] == "Preview failed (500)"
