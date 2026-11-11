# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read-only camera tools."""

from thin_mcp import ToolContext

from mcp_server import queries
from mcp_server.schemas import CameraSummary, Page, SceneListArguments
from mcp_server.tools_registry import READ_ANNOTATIONS, READ_PERMISSIONS, tool_registry


@tool_registry.register(
  name='list_cameras',
  description='List camera identity and pose-lock configuration, optionally filtered by scene UUID. '
              'Excludes stream URLs and credentials. Does not report live camera health.',
  arguments_model=SceneListArguments, result_model=Page[CameraSummary],
  permissions=READ_PERMISSIONS, annotations=READ_ANNOTATIONS,
)
def list_cameras(context: ToolContext, arguments: SceneListArguments) -> Page[CameraSummary]:
  """Adapt validated camera-list arguments to the inventory query."""
  return queries.list_cameras(arguments)
