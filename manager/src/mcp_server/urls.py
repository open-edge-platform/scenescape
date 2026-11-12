# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MCP transport routes."""

from django.urls import path

from mcp_server.api import McpEndpoint

urlpatterns = [path('', McpEndpoint.as_view(), name='mcp')]
