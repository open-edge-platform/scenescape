# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Register tools explicitly, in stable discovery order."""

from mcp_server.tools import scenes, cameras, regions
from mcp_server.tools_registry import tool_registry

__all__ = ['scenes', 'cameras', 'regions', 'tool_registry']
