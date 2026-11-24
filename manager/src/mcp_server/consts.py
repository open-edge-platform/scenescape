# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MCP method names, tool-call outcomes, and validation error identifiers."""

METHOD_TOOLS_CALL = 'tools/call'

OUTCOME_EXCEPTION = 'exception'
OUTCOME_PROTOCOL_ERROR = 'protocol_error'
OUTCOME_TOOL_ERROR = 'tool_error'
OUTCOME_SUCCESS = 'success'

# Pydantic's error type for malformed JSON, distinct from schema validation.
PYDANTIC_JSON_INVALID = 'json_invalid'
