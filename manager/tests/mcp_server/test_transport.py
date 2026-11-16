# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Exercise actual HTTP, authentication, and thin-mcp dispatch boundaries."""

import logging
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from django.conf import settings
from django.test import override_settings
from django.http import HttpRequest
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
    'list_scenes', 'get_scene',
  ]
  assert all(tool['annotations']['readOnlyHint'] for tool in tools)
  assert all(not tool['annotations']['destructiveHint'] for tool in tools)
  scene_fields = tools[0]['outputSchema']['$defs']['SceneSummary']['properties']
  assert set(scene_fields) == {'id', 'name', 'map_type', 'scale', 'use_tracker'}
  assert response['Cache-Control'] == 'no-store'


def test_missing_token_rejected(client):
  response = client.post('/', {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, format='json')
  assert response.status_code == 401
  assert response['WWW-Authenticate'] == 'Bearer'
  assert 'detail' in response.json()
  assert response['Cache-Control'] == 'no-store'


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


@pytest.mark.parametrize('failure, outcome', [
  (None, 'success'),
  (ToolExecutionError('private-tool-error'), 'tool_error'),
  (RuntimeError('internal-failure'), 'exception'),
])
def test_tool_calls_logged_once(client, monkeypatch, caplog, failure, outcome):
  """Log success and failures centrally, excluding arguments and returned data."""
  def list_scenes(arguments):
    if failure:
      raise failure
    scene = SceneSummary(id=uuid4(), name='private-scene-name',
                         map_type=None, scale=None, use_tracker=True)
    return Page(items=[scene], next_offset=None)

  monkeypatch.setattr(queries, 'list_scenes', list_scenes)
  with caplog.at_level(logging.INFO, logger='mcp_server.core'):
    rpc(client, 'tools/call', {'name': 'list_scenes', 'arguments': {'limit': 7}})
  entries = [record for record in caplog.records if record.getMessage().startswith('MCP tool call:')]
  assert len(entries) == 1
  message = entries[0].getMessage()
  assert f'tool=list_scenes user_id=1 outcome={outcome} duration_ms=' in message
  assert entries[0].levelno == logging.INFO
  assert all(value not in message for value in (
    'private-scene-name', 'private-tool-error', 'ephemeral-test-token', 'arguments', 'limit',
  ))


@pytest.mark.parametrize('name', ['untrusted\nname', {'private': 'value'}, None])
def test_invalid_tool_names_not_logged(client, caplog, name):
  """Unknown or malformed names cannot inject client-controlled text into logs."""
  with caplog.at_level(logging.INFO, logger='mcp_server.core'):
    rpc(client, 'tools/call', {'name': name, 'arguments': {}})
  messages = [record.getMessage() for record in caplog.records]
  assert len(messages) == 1
  assert 'tool=<unknown> user_id=1 outcome=protocol_error' in messages[0]
  assert 'untrusted' not in messages[0]
  assert 'private' not in messages[0]


def test_discovery_does_not_log_tool_call(client, caplog):
  with caplog.at_level(logging.INFO, logger='mcp_server.core'):
    rpc(client)
  assert not caplog.records


def test_pagination_follows_continuations_up_to_offset_500(client, monkeypatch):
  """Follow real tool calls to the last allowed page, then reject offset 501."""
  rows = [{'id': UUID(int=i + 1), 'name': f'Scene {i}', 'map_type': None,
           'scale': None, 'use_tracker': True} for i in range(526)]
  scene = MagicMock()
  # Use actual list slicing behind the ORM mock; keep validation and queries real.
  scene.objects.order_by.return_value.values.return_value = rows
  monkeypatch.setattr(queries, 'Scene', scene)
  offset = 0
  seen = []

  for expected_offset in range(0, 501, 25):
    assert offset == expected_offset
    response = rpc(client, 'tools/call', {
      'name': 'list_scenes', 'arguments': {'limit': 25, 'offset': offset},
    })
    assert response.status_code == 200
    page = response.json()['result']['structuredContent']
    assert [item['id'] for item in page['items']] == [
      str(row['id']) for row in rows[expected_offset:expected_offset + 25]]
    seen.extend(item['id'] for item in page['items'])
    offset = page['next_offset']

  assert offset is None  # Row 526 exists, but the next page would start above 500.
  assert len(seen) == len(set(seen)) == 525
  scene.objects.order_by.reset_mock()
  response = rpc(client, 'tools/call', {
    'name': 'list_scenes', 'arguments': {'offset': 501},
  })
  assert response.json()['result']['isError'] is True
  scene.objects.order_by.assert_not_called()


@pytest.mark.parametrize('arguments', [{'limit': 26}, {'limit': 0}, {'offset': -1},
                                       {'offset': 501}, {'unknown': 'value'}])
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


@pytest.mark.parametrize('body,code', [
  ('not-json', -32700), ('', -32700), (b'\xff', -32700),
  ('[]', -32600), ('{}', -32600),
  ('{"jsonrpc":"1.0","id":1,"method":"ping"}', -32600),
])
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


def test_json_media_type_with_charset(client):
  """Let DRF negotiate the JSON parser, including media-type parameters."""
  response = client.post('/', '{"jsonrpc":"2.0","id":1,"method":"ping"}',
                         content_type='application/json; charset=utf-8',
                         HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == 200
  assert 'result' in response.json()


@pytest.mark.parametrize('extra_bytes,status', [(0, 200), (1, 413)])
def test_request_size_boundary(client, extra_bytes, status):
  """Accept a valid request at the limit and reject one byte over it."""
  body = '{"jsonrpc":"2.0","id":1,"method":"ping"}'.ljust(settings.MCP_MAX_REQUEST_SIZE + extra_bytes)
  response = client.post('/', body, content_type='application/json',
                         HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == status
  assert response['Cache-Control'] == 'no-store'


def test_oversized_body_read_is_bounded(client):
  """The adapter reads only enough bytes to detect an oversized payload."""
  reads = []
  original_read = HttpRequest.read

  def bounded_read(request, size=-1):
    reads.append(size)
    return original_read(request, size)

  with patch.object(HttpRequest, 'read', bounded_read):
    response = client.post('/', 'x' * (settings.MCP_MAX_REQUEST_SIZE * 2), content_type='application/json',
                           HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == 413
  assert reads == [settings.MCP_MAX_REQUEST_SIZE + 1]
  assert response.json() == {'detail': 'Request too large.'}


@override_settings(MCP_MAX_REQUEST_SIZE=128)
@pytest.mark.parametrize('extra_bytes,status', [(0, 200), (1, 413)])
def test_configured_request_size_boundary(client, extra_bytes, status):
  """Apply the Django setting to both accepted and oversized requests."""
  body = '{"jsonrpc":"2.0","id":1,"method":"ping"}'.ljust(128 + extra_bytes)
  response = client.post('/', body, content_type='application/json',
                         HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == status


@pytest.mark.parametrize('method,status', [('get', 405), ('delete', 405)])
def test_http_errors_use_drf_responses(client, method, status):
  """DRF retains its error shape and method headers without custom conversion."""
  response = getattr(client, method)('/', HTTP_AUTHORIZATION='Bearer ephemeral-test-token')
  assert response.status_code == status
  assert 'detail' in response.json()
  assert 'POST' in response['Allow']
  assert response['Cache-Control'] == 'no-store'


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
  assert 'detail' in response.json()
  assert response['Cache-Control'] == 'no-store'
