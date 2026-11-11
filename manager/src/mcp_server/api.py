# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stateless JSON Streamable HTTP transport using Manager's API tokens."""

import json
import logging

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse, JsonResponse
from pydantic import ValidationError
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from thin_mcp import JsonRpcErrorCode, McpHttpResult, McpRequest, McpRequestHeaders

from mcp_server.core import process_request

logger = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 65536


class BearerTokenAuthentication(TokenAuthentication):
  """Accept MCP's Bearer scheme for the existing DRF token credential."""

  keyword = 'Bearer'


class McpThrottle(UserRateThrottle):
  """Bound per-user traffic using the configured Django cache."""

  scope = 'mcp'

  def get_rate(self) -> str:
    return getattr(settings, 'MCP_THROTTLE_RATE', '120/min')


def render_result(result: McpHttpResult) -> HttpResponse:
  """Serialize framework-neutral results and prevent shared response caching."""
  if result.body is None:
    response = HttpResponse(status=result.status)
  else:
    response = JsonResponse(result.body.model_dump(mode='json', by_alias=True), status=result.status)
  response['Cache-Control'] = 'no-store'
  return response


class McpEndpoint(APIView):
  """Expose read-only MCP tools to active authenticated API users."""

  authentication_classes = [BearerTokenAuthentication, TokenAuthentication]
  permission_classes = [IsAuthenticated]
  throttle_classes = [McpThrottle]
  renderer_classes = [JSONRenderer]
  http_method_names = ['post', 'options']

  def handle_exception(self, exc: Exception) -> HttpResponse:
    """Preserve DRF status/challenge headers while returning MCP error envelopes."""
    if not isinstance(exc, APIException):
      return super().handle_exception(exc)
    response = super().handle_exception(exc)
    result = render_result(McpHttpResult.error(
      None, JsonRpcErrorCode.SERVER_ERROR, str(exc.default_detail), status=response.status_code,
    ))
    for header in ('WWW-Authenticate', 'Retry-After', 'Allow'):
      if header in response:
        result[header] = response[header]
    return result

  def post(self, request: Request) -> HttpResponse:
    """Validate transport input, dispatch, and keep unexpected errors out of responses."""
    host = request.get_host()
    origin = request.headers.get('Origin')
    allowed_origins = {f'{request.scheme}://{host}', *getattr(settings, 'MCP_ALLOWED_ORIGINS', ())}
    if origin is not None and origin not in allowed_origins:
      return render_result(McpHttpResult.error(
        None, JsonRpcErrorCode.SERVER_ERROR, 'Origin not allowed.', status=403,
      ))
    if request.content_type != 'application/json':
      return render_result(McpHttpResult.error(
        None, JsonRpcErrorCode.INVALID_REQUEST, 'Expected application/json.', status=415,
      ))
    return self.dispatch_payload(request)

  def dispatch_payload(self, request: Request) -> HttpResponse:
    """Parse one bounded JSON-RPC request; batches are unsupported."""
    try:
      body = request.body
      if len(body) > MAX_REQUEST_BYTES:
        raise RequestDataTooBig
    except RequestDataTooBig:
      return render_result(McpHttpResult.error(
        None, JsonRpcErrorCode.INVALID_REQUEST, 'Request too large.', status=413,
      ))
    try:
      data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
      return render_result(McpHttpResult.error(
        None, JsonRpcErrorCode.PARSE_ERROR, 'Invalid JSON.', status=400,
      ))
    try:
      payload = McpRequest.model_validate(data)
    except ValidationError:
      return render_result(McpHttpResult.error(
        None, JsonRpcErrorCode.INVALID_REQUEST, 'Invalid MCP request.', status=400,
      ))
    try:
      result = process_request(request.user, payload, McpRequestHeaders.from_mapping(request.headers))
    except Exception:
      logger.exception('Unexpected MCP request failure.')
      result = McpHttpResult.error(
        payload.id, JsonRpcErrorCode.INTERNAL_ERROR, 'Internal server error.', status=500,
      )
    return render_result(result)
