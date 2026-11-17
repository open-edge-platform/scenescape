# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Delegate MCP protocol behavior to thin-mcp."""

import logging
from time import perf_counter

from django.contrib.auth.base_user import AbstractBaseUser
from pydantic import ValidationError
from thin_mcp import JsonRpcErrorCode, McpHttpResult, McpRequest, McpRequestHeaders, McpServer
from thin_mcp.schemas import JsonRpcErrorResponse, JsonRpcResultResponse, ToolResult

from mcp_server.consts import (
  OUTCOME_EXCEPTION, OUTCOME_PROTOCOL_ERROR, OUTCOME_SUCCESS, OUTCOME_TOOL_ERROR,
  PYDANTIC_JSON_INVALID,
)
from mcp_server.tools import tool_registry

logger = logging.getLogger(__name__)

MCP_SERVER = McpServer(
  name='scenescape', version='0.1.0',
  protocol_versions=('2025-03-26', '2025-06-18', '2025-11-25', '2026-07-28'),
  tools=tool_registry,
)


def dispatch_request(user: AbstractBaseUser, payload: McpRequest) -> McpHttpResult:
  """Log each tool call centrally without recording arguments or results."""
  if payload.method != 'tools/call':
    return MCP_SERVER.dispatch_request(user, payload)

  name = payload.params.get('name')
  # Only log registered names, never arbitrary client input or malformed params.
  tool = name if isinstance(name, str) and tool_registry.get(name) else '<unknown>'
  started = perf_counter()
  outcome = OUTCOME_EXCEPTION
  try:
    result = MCP_SERVER.dispatch_request(user, payload)
    match result.body:
      case JsonRpcErrorResponse():
        outcome = OUTCOME_PROTOCOL_ERROR
      case JsonRpcResultResponse(result=ToolResult(is_error=True)):
        outcome = OUTCOME_TOOL_ERROR
      case _:
        outcome = OUTCOME_SUCCESS
    return result
  finally:
    duration_ms = (perf_counter() - started) * 1000
    logger.info(f'MCP tool call: tool={tool} user_id={user.pk} '
                f'outcome={outcome} duration_ms={duration_ms:.1f}')


def process_request(user: AbstractBaseUser, body: bytes,
                    headers: McpRequestHeaders) -> McpHttpResult:
  """Validate JSON and the MCP envelope once, then delegate protocol dispatch."""
  try:
    payload = McpRequest.model_validate_json(body)
  except ValidationError as exc:
    if any(error['type'] == PYDANTIC_JSON_INVALID for error in exc.errors()):
      return McpHttpResult.error(None, JsonRpcErrorCode.PARSE_ERROR, 'Invalid JSON.', status=400)
    return McpHttpResult.error(None, JsonRpcErrorCode.INVALID_REQUEST, 'Invalid MCP request.', status=400)

  try:
    result = MCP_SERVER.validate_http_request(payload, headers)
    if result is not None:
      return result
    return dispatch_request(user, payload)
  except Exception:
    logger.exception('Unexpected MCP request failure.')
    return McpHttpResult.error(
      payload.id, JsonRpcErrorCode.INTERNAL_ERROR, 'Internal server error.', status=500,
    )
