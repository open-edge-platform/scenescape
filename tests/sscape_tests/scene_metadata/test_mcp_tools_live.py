# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Verify MCP tool functions against a running Scene Metadata HTTP server."""

import json
import os
import subprocess
import time
import uuid

import pytest
import urllib.request

pytestmark = pytest.mark.test_name('SC-SceneMetadata-MCP-Live')

pytestmark_live = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_RUN_LIVE'),
  reason='Set SCENE_METADATA_RUN_LIVE=1 with server on SCENE_METADATA_API_URL',
)


@pytestmark_live
def test_mcp_tools_against_live_api():
  base = os.environ.get('SCENE_METADATA_API_URL', 'http://127.0.0.1:8080').rstrip('/')
  with urllib.request.urlopen(f'{base}/v1/health', timeout=5) as resp:
    health = json.loads(resp.read().decode())
  assert health['status'] == 'ok'

  os.environ['SCENE_METADATA_API_URL'] = base
  from scene_metadata.api_client import get_json, post_json

  status = get_json('/v1/health')
  assert status['component'] == 'scene-metadata'

  query = post_json('/v1/events/query', {'limit': 5})
  assert 'events' in query
