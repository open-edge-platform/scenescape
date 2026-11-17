# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""One registry shared by explicit domain tool imports."""

from thin_mcp import ToolAnnotations, ToolRegistry


tool_registry = ToolRegistry()
READ_ANNOTATIONS = ToolAnnotations(
  readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
)
