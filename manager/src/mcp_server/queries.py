# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bounded inventory queries; select only fields in the public MCP contract."""

from django.db.models import QuerySet
from thin_mcp import ToolExecutionError

from manager.models import Scene
from mcp_server.schemas import (
  MAX_OFFSET, ItemT, ListArguments, Page, SceneArguments, SceneSummary,
)


def inventory_page(queryset: QuerySet, arguments: ListArguments,
                   item_model: type[ItemT]) -> Page[ItemT]:
  """Fetch one extra row to detect another page without an unbounded count."""
  rows = list(queryset.values(*item_model.model_fields)[
    arguments.offset:arguments.offset + arguments.limit + 1])
  next_offset = arguments.offset + arguments.limit
  if len(rows) <= arguments.limit or next_offset > MAX_OFFSET:
    next_offset = None
  return Page[item_model](
    items=[item_model.model_validate(row) for row in rows[:arguments.limit]],
    next_offset=next_offset,
  )


def list_scenes(arguments: ListArguments) -> Page[SceneSummary]:
  """Return persisted scene metadata, without nested cameras or map files."""
  return inventory_page(Scene.objects.order_by('id'), arguments, SceneSummary)


def get_scene(arguments: SceneArguments) -> SceneSummary:
  """Resolve one scene; missing scenes are expected tool errors."""
  row = Scene.objects.filter(pk=arguments.scene_id).values(*SceneSummary.model_fields).first()
  if row is None:
    raise ToolExecutionError('Scene not found.')
  return SceneSummary.model_validate(row)
