# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read-only scene tools."""

from thin_mcp import ToolContext

from mcp_server import queries
from mcp_server.schemas import ListArguments, Page, SceneArguments, SceneSummary
from mcp_server.tools_registry import READ_ANNOTATIONS, READ_PERMISSIONS, tool_registry


@tool_registry.register(
  name='list_scenes', description='List persisted scene configuration, up to 25 per page.',
  arguments_model=ListArguments, result_model=Page[SceneSummary],
  permissions=READ_PERMISSIONS, annotations=READ_ANNOTATIONS,
)
def list_scenes(context: ToolContext, arguments: ListArguments) -> Page[SceneSummary]:
  """Adapt validated scene-list arguments to the inventory query."""
  return queries.list_scenes(arguments)


@tool_registry.register(
  name='get_scene', description='Get persisted configuration for one scene by UUID.',
  arguments_model=SceneArguments, result_model=SceneSummary,
  permissions=READ_PERMISSIONS, annotations=READ_ANNOTATIONS,
)
def get_scene(context: ToolContext, arguments: SceneArguments) -> SceneSummary:
  """Adapt a validated scene identifier to the inventory query."""
  return queries.get_scene(arguments)
