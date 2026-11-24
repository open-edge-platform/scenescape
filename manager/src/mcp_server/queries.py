# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bounded inventory queries; select only fields in the public MCP contract."""

from django.core.paginator import EmptyPage, Paginator
from django.db.models import QuerySet
from thin_mcp import ToolExecutionError

from manager.models import Scene
from mcp_server.schemas import (
  ItemT, ListArguments, Page, SceneArguments, SceneSummary,
)


def inventory_page(queryset: QuerySet, arguments: ListArguments,
                   item_model: type[ItemT]) -> Page[ItemT]:
  """Paginate projected fields using the same Django paginator as the REST API."""
  paginator = Paginator(queryset.values(*item_model.model_fields), arguments.limit)
  try:
    page = paginator.page(arguments.page)
  except EmptyPage as exc:
    raise ToolExecutionError('Page does not exist.') from exc
  return Page[item_model](
    items=[item_model.model_validate(row) for row in page.object_list],
    next_page=page.next_page_number() if page.has_next() else None,
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
