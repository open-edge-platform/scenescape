# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Read-only region tools."""

from thin_mcp import ToolContext

from mcp_server import queries
from mcp_server.schemas import Page, RegionSummary, SceneListArguments
from mcp_server.tools_registry import READ_ANNOTATIONS, READ_PERMISSIONS, tool_registry


@tool_registry.register(
  name='list_regions',
  description='List region configuration, optionally filtered by scene UUID. '
              'Does not report live occupancy or tracked objects.',
  arguments_model=SceneListArguments, result_model=Page[RegionSummary],
  permissions=READ_PERMISSIONS, annotations=READ_ANNOTATIONS,
)
def list_regions(context: ToolContext, arguments: SceneListArguments) -> Page[RegionSummary]:
  """Adapt validated region-list arguments to the inventory query."""
  return queries.list_regions(arguments)
