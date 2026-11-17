# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Stable tool-call log outcomes and validation error identifiers."""

OUTCOME_EXCEPTION = 'exception'
OUTCOME_PROTOCOL_ERROR = 'protocol_error'
OUTCOME_TOOL_ERROR = 'tool_error'
OUTCOME_SUCCESS = 'success'

# Pydantic's error type for malformed JSON, distinct from schema validation.
PYDANTIC_JSON_INVALID = 'json_invalid'
