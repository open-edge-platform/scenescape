# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exercise actual HTTP, authentication, and thin-mcp dispatch boundaries."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from django.test import override_settings
from rest_framework.authtoken.models import Token
from thin_mcp import ToolExecutionError

from mcp_server import queries
from mcp_server.schemas import Page, SceneSummary


def rpc(client, method='tools/list', params=None, **headers):
  """Send a normal MCP request using an ephemeral test-only credential."""
  return client.post('/', {
    'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {},
  }, format='json', HTTP_AUTHORIZATION='Bearer ephemeral-test-token', **headers)


@pytest.mark.parametrize('scheme', ['Bearer', 'Token'])
def test_discovery_authentication_and_read_only_contract(client, scheme):
  response = client.post('/', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                         format='json', HTTP_AUTHORIZATION=f'{scheme} ephemeral-test-token')
  assert response.status_code == 200
  tools = response.json()['result']['tools']
  assert [tool['name'] for tool in tools] == [
    'list_scenes', 'get_scene', 'list_cameras', 'list_regions',
  ]
  assert all(tool['annotations']['readOnlyHint'] for tool in tools)
  assert all(not tool['annotations']['destructiveHint'] for tool in tools)
  camera_fields = tools[2]['outputSchema']['$defs']['CameraSummary']['properties']
  assert set(camera_fields) == {'sensor_id', 'name', 'scene_id', 'pose_locked'}
  assert response['Cache-Control'] == 'no-store'


def test_missing_token_rejected(client):
  response = client.post('/', {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, format='json')
  assert response.status_code == 401
  assert response['WWW-Authenticate'] == 'Bearer'
  assert 'error' in response.json()


def test_invalid_token_rejected(client):
  with patch.object(Token.objects, 'get', side_effect=Token.DoesNotExist):
    assert rpc(client).status_code == 401


def test_inactive_user_rejected(client, user):
  user.is_active = False
  assert rpc(client).status_code == 401


def test_initialize_and_notification(client):
  response = rpc(client, 'initialize', {
    'protocolVersion': '2025-11-25', 'capabilities': {},
    'clientInfo': {'name': 'test', 'version': '1'},
  })
  assert response.status_code == 200
  assert response.json()['result']['serverInfo']['name'] == 'scenescape'
  response = client.post('/', {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                         format='json', HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == 202
  assert response.content == b''


def test_valid_tool_call(client, monkeypatch):
  scene = SceneSummary(id=uuid4(), name='Demo', map_type='map_upload', scale=1, use_tracker=True)
  monkeypatch.setattr(queries, 'list_scenes', lambda arguments: Page(items=[scene], next_offset=None))
  response = rpc(client, 'tools/call', {'name': 'list_scenes', 'arguments': {'limit': 1}})
  result = response.json()['result']
  assert result['structuredContent']['items'][0]['id'] == str(scene.id)
  assert result['structuredContent']['next_offset'] is None


@pytest.mark.parametrize('arguments', [{'limit': 26}, {'limit': 0}, {'offset': -1},
                                      {'offset': 100001}, {'unknown': 'value'}])
def test_invalid_tool_arguments_never_query(client, monkeypatch, arguments):
  def unexpected_query(arguments):
    raise AssertionError('Invalid arguments reached the query layer.')
  monkeypatch.setattr(queries, 'list_scenes', unexpected_query)
  result = rpc(client, 'tools/call', {'name': 'list_scenes', 'arguments': arguments}).json()
  assert result['result']['isError'] is True


def test_missing_scene_is_tool_error(client, monkeypatch):
  def missing(arguments):
    raise ToolExecutionError('Scene not found.')
  monkeypatch.setattr(queries, 'get_scene', missing)
  result = rpc(client, 'tools/call', {
    'name': 'get_scene', 'arguments': {'scene_id': str(uuid4())},
  }).json()
  assert result['result']['isError'] is True
  assert result['result']['content'][0]['text'] == 'Scene not found.'


def test_unexpected_errors_do_not_leak(client, monkeypatch):
  def broken(arguments):
    raise RuntimeError('private backend detail')
  monkeypatch.setattr(queries, 'list_scenes', broken)
  response = rpc(client, 'tools/call', {'name': 'list_scenes', 'arguments': {}})
  assert response.status_code == 500
  assert 'private backend detail' not in response.content.decode()
  assert response.json()['error']['code'] == -32603


@pytest.mark.parametrize('body,code', [('not-json', -32700), ('[]', -32600), ('{}', -32600)])
def test_malformed_requests(client, body, code):
  response = client.post('/', body, content_type='application/json',
                         HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == 400
  assert response.json()['error']['code'] == code


def test_transport_limits(client):
  assert client.post('/', 'x', content_type='text/plain',
                     HTTP_AUTHORIZATION='Bearer ephemeral-test-token').status_code == 415
  assert client.post('/', 'x' * 65537, content_type='application/json',
                     HTTP_AUTHORIZATION='Bearer ephemeral-test-token').status_code == 413
  assert client.get('/', HTTP_AUTHORIZATION='Bearer ephemeral-test-token').status_code == 405


def test_origin_validation(client):
  assert rpc(client, HTTP_ORIGIN='https://untrusted.example').status_code == 403
  assert rpc(client, HTTP_ORIGIN='http://testserver').status_code == 200
  with override_settings(MCP_ALLOWED_ORIGINS=['https://trusted.example']):
    assert rpc(client, HTTP_ORIGIN='https://trusted.example').status_code == 200


def test_protocol_headers_validated(client):
  assert rpc(client, HTTP_MCP_PROTOCOL_VERSION='invalid').status_code == 400
  metadata = {'_meta': {
    'io.modelcontextprotocol/protocolVersion': '2026-07-28',
    'io.modelcontextprotocol/clientCapabilities': {},
  }}
  assert rpc(client, params=metadata, HTTP_MCP_PROTOCOL_VERSION='2026-07-28').status_code == 400
  response = rpc(client, params=metadata, HTTP_MCP_PROTOCOL_VERSION='2026-07-28',
                 HTTP_MCP_METHOD='tools/list')
  assert response.status_code == 200, response.content
  assert response.json()['result']['ttlMs'] == 0


def test_throttle(client):
  with override_settings(MCP_THROTTLE_RATE='1/min'):
    assert rpc(client).status_code == 200
    response = rpc(client)
  assert response.status_code == 429
  assert 'Retry-After' in response
