# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Delegate MCP protocol behavior to thin-mcp."""

import logging

from django.contrib.auth.base_user import AbstractBaseUser
from pydantic import ValidationError
from thin_mcp import JsonRpcErrorCode, McpHttpResult, McpRequest, McpRequestHeaders, McpServer

from mcp_server.tools import tool_registry

logger = logging.getLogger(__name__)

MCP_SERVER = McpServer(
  name='scenescape', version='0.1.0',
  protocol_versions=('2025-03-26', '2025-06-18', '2025-11-25', '2026-07-28'),
  tools=tool_registry,
)


def process_request(user: AbstractBaseUser, body: bytes,
                    headers: McpRequestHeaders) -> McpHttpResult:
  """Validate JSON and the MCP envelope once, then delegate protocol dispatch."""
  try:
    payload = McpRequest.model_validate_json(body)
  except ValidationError as exc:
    if any(error['type'] == 'json_invalid' for error in exc.errors()):
      return McpHttpResult.error(None, JsonRpcErrorCode.PARSE_ERROR, 'Invalid JSON.', status=400)
    return McpHttpResult.error(None, JsonRpcErrorCode.INVALID_REQUEST, 'Invalid MCP request.', status=400)

  try:
    result = MCP_SERVER.validate_http_request(payload, headers)
    return result if result is not None else MCP_SERVER.dispatch_request(user, payload)
  except Exception:
    logger.exception('Unexpected MCP request failure.')
    return McpHttpResult.error(
      payload.id, JsonRpcErrorCode.INTERNAL_ERROR, 'Internal server error.', status=500,
    )
