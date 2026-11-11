# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""One registry shared by explicit domain tool imports."""

from pydantic import BaseModel
from thin_mcp import ToolAnnotations, ToolContext, ToolPermissionDenied, ToolRegistry


class AuthenticatedReader:
  """Match Manager's API read policy: an active authenticated user."""

  def check(self, context: ToolContext, arguments: BaseModel) -> None:
    if not context.user or not context.user.is_authenticated or not context.user.is_active:
      raise ToolPermissionDenied('Authentication required.')


tool_registry = ToolRegistry()
READ_PERMISSIONS = (AuthenticatedReader(),)
READ_ANNOTATIONS = ToolAnnotations(
  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
)
