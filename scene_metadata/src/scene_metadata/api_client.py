# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""HTTP client for Scene Metadata query API (shared by MCP and tests)."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


def api_base() -> str:
  return os.environ.get('SCENE_METADATA_API_URL', 'http://127.0.0.1:8080').rstrip('/')


def get_json(path: str, query: dict | None = None) -> dict:
  url = api_base() + path
  if query:
    params = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    if params:
      url = f'{url}?{params}'
  request = urllib.request.Request(url, headers={'Accept': 'application/json'})
  try:
    with urllib.request.urlopen(request, timeout=30) as response:
      return json.loads(response.read().decode('utf-8'))
  except urllib.error.HTTPError as err:
    body = err.read().decode('utf-8', errors='replace')
    raise RuntimeError(f'API {path} failed ({err.code}): {body}') from err


def post_json(path: str, payload: dict) -> dict:
  data = json.dumps(payload).encode('utf-8')
  request = urllib.request.Request(
    api_base() + path,
    data=data,
    headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    method='POST',
  )
  with urllib.request.urlopen(request, timeout=30) as response:
    return json.loads(response.read().decode('utf-8'))


def mcp_personas() -> set[str]:
  return {
    p.strip()
    for p in os.environ.get(
      'SCENE_METADATA_MCP_PERSONAS', 'investigator,operator,integrator').split(',')
    if p.strip()
  }


def persona_allowed(name: str) -> bool:
  return name in mcp_personas()
