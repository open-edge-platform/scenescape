# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""DRF hooks for authenticated, bounded MCP HTTP requests."""

from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import APIException
from rest_framework.parsers import BaseParser
from rest_framework.permissions import BasePermission
from rest_framework.throttling import UserRateThrottle


class BearerTokenAuthentication(TokenAuthentication):
  """Accept Bearer credentials using Manager's existing API tokens."""

  keyword = 'Bearer'


class McpThrottle(UserRateThrottle):
  """Apply the configured per-user MCP rate limit."""

  scope = 'mcp'

  def get_rate(self) -> str:
    return getattr(settings, 'MCP_THROTTLE_RATE', '120/min')


class AllowedOrigin(BasePermission):
  """Check Origin because token-authenticated DRF views skip CSRF checks."""

  message = 'Origin not allowed.'

  def has_permission(self, request, view) -> bool:
    host = request.get_host()  # Delegate host validation to Django's ALLOWED_HOSTS.
    origin = request.headers.get('Origin')
    allowed = {f'{request.scheme}://{host}', *getattr(settings, 'MCP_ALLOWED_ORIGINS', ())}
    return origin is None or origin in allowed


class RequestTooLarge(APIException):
  status_code = 413
  default_detail = 'Request too large.'
  default_code = 'request_too_large'


class McpParser(BaseParser):
  """Read bounded JSON bytes; the MCP core validates them with Pydantic."""

  media_type = 'application/json'

  def parse(self, stream, media_type=None, parser_context=None) -> bytes:
    # JSONParser buffers the body under Django's larger global upload limit.
    # BaseParser keeps this read bounded; DRF still selects the media type.
    body = stream.read(settings.MCP_MAX_REQUEST_SIZE + 1)
    if len(body) > settings.MCP_MAX_REQUEST_SIZE:
      raise RequestTooLarge
    return body
