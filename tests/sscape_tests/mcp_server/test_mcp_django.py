# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MCP integration with real Manager models, migrations, and a Django test DB."""

from uuid import UUID

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager.models import Scene

pytestmark = pytest.mark.django_db


@pytest.fixture
def mcp_client():
  """Create a real user, token and scenes for each test."""
  user = User.objects.create_user(username='mcp_reader')
  token = Token.objects.create(user=user)
  Scene.objects.bulk_create([
    Scene(id=UUID(int=i), name=f'Scene {i}', map_type=None, scale=None,
          use_tracker=True, dataset_dir='private-dataset', output_dir='private-output')
    for i in (3, 1, 2)
  ])
  cache.clear()
  client = APIClient(enforce_csrf_checks=True)
  client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')
  yield client, user, token
  cache.clear()


def rpc(client, method, params=None):
  """Use the production /mcp route and real token lookup."""
  return client.post('/mcp', {
    'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {},
  }, format='json', secure=True)


def call_tool(client, name, arguments):
  response = rpc(client, 'tools/call', {'name': name, 'arguments': arguments})
  assert response.status_code == 200, response.content
  return response.json()['result']


def test_initialize_and_discover_two_read_only_tools(mcp_client):
  client, _, _ = mcp_client
  response = rpc(client, 'initialize', {
    'protocolVersion': '2025-11-25', 'capabilities': {},
    'clientInfo': {'name': 'django-integration', 'version': '1'},
  })
  assert response.status_code == 200
  response = rpc(client, 'tools/list')
  assert response.status_code == 200
  tools = response.json()['result']['tools']
  assert [tool['name'] for tool in tools] == ['list_scenes', 'get_scene']
  assert all(tool['annotations']['readOnlyHint'] for tool in tools)


def test_list_scenes_orders_and_projects_real_rows(mcp_client):
  client, _, _ = mcp_client
  result = call_tool(client, 'list_scenes', {'limit': 2})['structuredContent']
  assert result['next_offset'] == 2
  assert result['items'] == [
    {'id': str(UUID(int=i)), 'name': f'Scene {i}', 'map_type': None,
     'scale': None, 'use_tracker': True} for i in (1, 2)
  ]
  last = call_tool(client, 'list_scenes', {'limit': 2, 'offset': 2})['structuredContent']
  assert [row['id'] for row in last['items']] == [str(UUID(int=3))]
  assert last['next_offset'] is None


def test_get_scene_is_read_only(mcp_client):
  client, _, _ = mcp_client
  Scene.objects.filter(pk=UUID(int=2)).update(map_type='map_upload', scale=2.5, use_tracker=False)
  with CaptureQueriesContext(connection) as captured:
    result = call_tool(client, 'get_scene', {'scene_id': str(UUID(int=2))})
  assert result['structuredContent'] == {
    'id': str(UUID(int=2)), 'name': 'Scene 2', 'map_type': 'map_upload',
    'scale': 2.5, 'use_tracker': False,
  }
  assert captured.captured_queries
  assert all(query['sql'].lstrip().upper().startswith('SELECT') for query in captured)
  assert Scene.objects.count() == 3


def test_missing_scene_returns_tool_error(mcp_client):
  client, _, _ = mcp_client
  result = call_tool(client, 'get_scene', {'scene_id': str(UUID(int=999))})
  assert result['isError']
  assert result['content'][0]['text'] == 'Scene not found.'


def test_pagination_stops_after_page_start_500(mcp_client):
  client, _, _ = mcp_client
  Scene.objects.bulk_create([Scene(id=UUID(int=i), name=f'Scene {i}') for i in range(4, 527)])
  offset = 0
  seen = []
  for expected_offset in range(0, 501, 25):
    assert offset == expected_offset
    page = call_tool(client, 'list_scenes', {'offset': offset})['structuredContent']
    seen.extend(row['id'] for row in page['items'])
    offset = page['next_offset']
  assert offset is None
  assert seen == [str(UUID(int=i)) for i in range(1, 526)]
  assert Scene.objects.count() == 526


@pytest.mark.parametrize('tool, arguments', [
  ('list_scenes', {'offset': 501}),
  ('get_scene', {'scene_id': 'not-a-uuid'}),
])
def test_invalid_arguments_only_query_authentication(mcp_client, django_assert_num_queries, tool, arguments):
  client, _, _ = mcp_client
  with django_assert_num_queries(1):
    result = call_tool(client, tool, arguments)
  assert result['isError']


def test_revoked_token_is_rejected(mcp_client):
  client, _, token = mcp_client
  token.delete()
  response = rpc(client, 'tools/list')
  assert response.status_code == 401
  assert response['WWW-Authenticate'] == 'Bearer'


def test_inactive_user_is_rejected(mcp_client):
  client, user, _ = mcp_client
  User.objects.filter(pk=user.pk).update(is_active=False)
  assert rpc(client, 'tools/list').status_code == 401
