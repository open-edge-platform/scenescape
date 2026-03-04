#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Mock Manager REST API server for tracker service tests.

Implements the two endpoints the tracker uses:
  POST /api/v1/auth  - returns auth token
  GET  /api/v1/scenes - returns scene list (requires token)

Serves a real Manager API response (complete JSON with count, next, previous, results).
The tracker's ApiSceneLoader extracts the results array and transforms it to nested schema format.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

SCENES_PATH = os.environ.get("MOCK_SCENES_PATH", "/data/scenes.json")
LISTEN_PORT = int(os.environ.get("MOCK_PORT", "8000"))
TOKEN = "mock-test-token-12345"


def load_scenes():
  with open(SCENES_PATH) as f:
    return json.load(f)


class MockManagerHandler(BaseHTTPRequestHandler):
  """Minimal handler implementing Manager auth and scenes endpoints."""

  def do_POST(self):
    if self.path == "/api/v1/auth":
      self._handle_auth()
    else:
      self._send_json(404, {"detail": "Not found."})

  def do_GET(self):
    if self.path == "/healthz":
      self._send_json(200, {"status": "ok"})
    elif self.path == "/api/v1/scenes":
      self._handle_scenes()
    else:
      self._send_json(404, {"detail": "Not found."})

  def _handle_auth(self):
    content_length = int(self.headers.get("Content-Length", 0))
    body = self.rfile.read(content_length).decode()
    params = parse_qs(body)

    username = params.get("username", [None])[0]
    password = params.get("password", [None])[0]

    if not username or not password:
      self._send_json(
          400, {
              "non_field_errors": ["Unable to log in with provided credentials."]})
      return

    self._send_json(200, {"token": TOKEN})

  def _handle_scenes(self):
    auth = self.headers.get("Authorization", "")
    if auth != f"Token {TOKEN}":
      self._send_json(
          401, {
              "detail": "Authentication credentials were not provided."})
      return

    scenes_response = load_scenes()
    self._send_json(200, scenes_response)

  def _send_json(self, code, data):
    body = json.dumps(data).encode()
    self.send_response(code)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def log_message(self, format, *args):
    """Log to stdout for docker compose logs visibility."""
    print(f"[mock-manager] {args[0]}")


if __name__ == "__main__":
  server = HTTPServer(("0.0.0.0", LISTEN_PORT), MockManagerHandler)
  print(
      f"[mock-manager] Listening on port {LISTEN_PORT}, scenes: {SCENES_PATH}")
  server.serve_forever()
