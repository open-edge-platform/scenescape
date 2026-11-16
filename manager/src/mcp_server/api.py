# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Expose the MCP core through Manager's Django REST Framework endpoint."""

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from thin_mcp import McpRequestHeaders

from mcp_server.core import process_request
from mcp_server.transport import AllowedOrigin, BearerTokenAuthentication, McpParser, McpThrottle


@method_decorator(cache_control(no_store=True), name='dispatch')
class McpEndpoint(APIView):
  """Expose read-only MCP tools to active authenticated API users."""

  authentication_classes = [BearerTokenAuthentication, TokenAuthentication]
  permission_classes = [IsAuthenticated, AllowedOrigin]
  throttle_classes = [McpThrottle]
  parser_classes = [McpParser]
  renderer_classes = [JSONRenderer]
  http_method_names = ['post', 'options']

  def post(self, request: Request) -> Response:
    """Pass bounded request bytes to MCP and render its response."""
    # DRF supplies an empty dict for requests without a body.
    result = process_request(request.user, request.data or b'',
                             McpRequestHeaders.from_mapping(request.headers))
    body = result.body.model_dump(mode='json', by_alias=True) if result.body is not None else None
    return Response(body, status=result.status)
