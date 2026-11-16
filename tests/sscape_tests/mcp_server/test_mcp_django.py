# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MCP integration with real Manager models, migrations, and a Django test DB."""

from uuid import UUID

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager.models import Scene


class TestMcpDatabase(TestCase):
  """Exercise /mcp through Manager's URL configuration without database mocks."""

  @classmethod
  def setUpTestData(cls):
    cls.user = User.objects.create_user(username='mcp_reader')
    cls.token = Token.objects.create(user=cls.user)
    # Deliberately insert out of UUID order and include nullable/private fields.
    Scene.objects.bulk_create([
      Scene(id=UUID(int=i), name=f'Scene {i}', map_type=None, scale=None,
            use_tracker=True, dataset_dir='private-dataset', output_dir='private-output')
      for i in (3, 1, 2)
    ])

  def setUp(self):
    cache.clear()
    self.addCleanup(cache.clear)
    self.client = APIClient(enforce_csrf_checks=True)
    self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token.key}')

  def rpc(self, method, params=None):
    """Use the production /mcp route and real token lookup."""
    return self.client.post('/mcp', {
      'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {},
    }, format='json', secure=True)

  def call_tool(self, name, arguments):
    response = self.rpc('tools/call', {'name': name, 'arguments': arguments})
    self.assertEqual(response.status_code, 200, response.content)
    return response.json()['result']

  def test_initialize_and_discover_two_read_only_tools(self):
    """A real regular-user token can initialize and discover only scene tools."""
    response = self.rpc('initialize', {
      'protocolVersion': '2025-11-25', 'capabilities': {},
      'clientInfo': {'name': 'django-integration', 'version': '1'},
    })
    self.assertEqual(response.status_code, 200)
    response = self.rpc('tools/list')
    self.assertEqual(response.status_code, 200)
    tools = response.json()['result']['tools']
    self.assertEqual([tool['name'] for tool in tools], ['list_scenes', 'get_scene'])
    self.assertTrue(all(tool['annotations']['readOnlyHint'] for tool in tools))

  def test_list_scenes_orders_and_projects_real_rows(self):
    """Real ORM projections omit private fields and preserve null values."""
    result = self.call_tool('list_scenes', {'limit': 2})['structuredContent']
    self.assertEqual(result['next_offset'], 2)
    self.assertEqual(result['items'], [
      {'id': str(UUID(int=i)), 'name': f'Scene {i}', 'map_type': None,
       'scale': None, 'use_tracker': True} for i in (1, 2)
    ])
    last = self.call_tool('list_scenes', {'limit': 2, 'offset': 2})['structuredContent']
    self.assertEqual([row['id'] for row in last['items']], [str(UUID(int=3))])
    self.assertIsNone(last['next_offset'])

  def test_get_scene_is_read_only(self):
    """Lookup returns persisted fields without issuing a database write."""
    Scene.objects.filter(pk=UUID(int=2)).update(map_type='map_upload', scale=2.5, use_tracker=False)
    with CaptureQueriesContext(connection) as captured:
      result = self.call_tool('get_scene', {'scene_id': str(UUID(int=2))})
    self.assertEqual(result['structuredContent'], {
      'id': str(UUID(int=2)), 'name': 'Scene 2', 'map_type': 'map_upload',
      'scale': 2.5, 'use_tracker': False,
    })
    self.assertTrue(captured.captured_queries)
    self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in captured))
    self.assertEqual(Scene.objects.count(), 3)

  def test_missing_scene_returns_tool_error(self):
    """A UUID absent from the actual database produces an expected tool error."""
    result = self.call_tool('get_scene', {'scene_id': str(UUID(int=999))})
    self.assertTrue(result['isError'])
    self.assertEqual(result['content'][0]['text'], 'Scene not found.')

  def test_pagination_stops_after_page_start_500(self):
    """Follow real SQL-backed pages without duplicates or an invalid continuation."""
    Scene.objects.bulk_create([
      Scene(id=UUID(int=i), name=f'Scene {i}') for i in range(4, 527)
    ])
    offset = 0
    seen = []
    for expected_offset in range(0, 501, 25):
      self.assertEqual(offset, expected_offset)
      page = self.call_tool('list_scenes', {'offset': offset})['structuredContent']
      seen.extend(row['id'] for row in page['items'])
      offset = page['next_offset']
    self.assertIsNone(offset)
    self.assertEqual(seen, [str(UUID(int=i)) for i in range(1, 526)])
    self.assertEqual(Scene.objects.count(), 526)

  def test_invalid_arguments_only_query_authentication(self):
    """Reject invalid offsets and UUIDs before querying scene data."""
    for tool, arguments in [('list_scenes', {'offset': 501}),
                            ('get_scene', {'scene_id': 'not-a-uuid'})]:
      with self.subTest(tool=tool), self.assertNumQueries(1):
        result = self.call_tool(tool, arguments)
      self.assertTrue(result['isError'])

  def test_revoked_token_is_rejected(self):
    """Deleting a real token immediately removes access."""
    Token.objects.filter(pk=self.token.key).delete()
    response = self.rpc('tools/list')
    self.assertEqual(response.status_code, 401)
    self.assertEqual(response['WWW-Authenticate'], 'Bearer')

  def test_inactive_user_is_rejected(self):
    """A token belonging to a deactivated database user cannot access tools."""
    User.objects.filter(pk=self.user.pk).update(is_active=False)
    self.assertEqual(self.rpc('tools/list').status_code, 401)
