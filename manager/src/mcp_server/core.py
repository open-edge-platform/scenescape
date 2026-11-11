# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Delegate MCP protocol behavior to thin-mcp."""

from django.contrib.auth.base_user import AbstractBaseUser
from thin_mcp import McpHttpResult, McpRequest, McpRequestHeaders, McpServer

from mcp_server.tools import tool_registry

MCP_SERVER = McpServer(
  name='scenescape', version='0.1.0',
  protocol_versions=('2025-03-26', '2025-06-18', '2025-11-25', '2026-07-28'),
  tools=tool_registry,
)


def process_request(user: AbstractBaseUser, payload: McpRequest,
                    headers: McpRequestHeaders) -> McpHttpResult:
  """Validate protocol headers before executing an authenticated request."""
  result = MCP_SERVER.validate_http_request(payload, headers)
  if result is not None:
    return result
  return MCP_SERVER.dispatch_request(user, payload)
